"""SQLite connection management — WAL mode, single writer thread."""

from __future__ import annotations

import queue
import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from server.store.migrate import migrate

T = TypeVar("T")
WRITE_QUEUE_SIZE = 256

_WriteFn = Callable[[sqlite3.Connection], object]
_QueueItem = tuple[_WriteFn | None, queue.Queue[object]]


def connect(db_path: Path) -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode enabled."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class Database:
    """SQLite database with a single writer thread and bounded write queue."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._write_queue: queue.Queue[_QueueItem] = queue.Queue(maxsize=WRITE_QUEUE_SIZE)
        self._reader = connect(db_path)
        migrate(self._reader)
        self._writer_conn = connect(db_path)
        self._thread = threading.Thread(
            target=self._writer_loop, name="cairn-db-writer", daemon=True
        )
        self._thread.start()

    @property
    def reader(self) -> sqlite3.Connection:
        """Return the read connection (use only on reader thread / tests)."""
        return self._reader

    def _writer_loop(self) -> None:
        while True:
            item = self._write_queue.get()
            fn, reply_q = item
            if fn is None:  # shutdown sentinel
                return
            try:
                result = fn(self._writer_conn)
                self._writer_conn.commit()
                reply_q.put(result)
            except Exception as exc:
                self._writer_conn.rollback()
                reply_q.put(exc)

    def write(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Execute a write transaction on the single writer thread."""
        reply_q: queue.Queue[object] = queue.Queue(maxsize=1)
        self._write_queue.put((fn, reply_q))
        result = reply_q.get()
        if isinstance(result, Exception):
            raise result
        return result  # type: ignore[return-value]

    def close(self) -> None:
        """Shut down writer thread and close connections."""
        reply_q: queue.Queue[object] = queue.Queue(maxsize=1)
        self._write_queue.put((None, reply_q))
        self._thread.join(timeout=5)
        self._reader.close()
        self._writer_conn.close()
