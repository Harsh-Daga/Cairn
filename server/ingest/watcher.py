"""File watchers with bounded queues and path coalescing."""

from __future__ import annotations

import contextlib
import queue
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

QUEUE_SIZE = 256
_POLL_INTERVAL_SEC = 0.5

OnChange = Callable[[Path], None]


@dataclass(frozen=True)
class WatchEvent:
    """Filesystem change notification."""

    path: Path
    mtime_ns: int


class FileWatcher:
    """Poll watched paths and emit coalesced change events."""

    def __init__(self, *, queue_size: int = QUEUE_SIZE) -> None:
        self._queue: queue.Queue[WatchEvent | None] = queue.Queue(maxsize=queue_size)
        self._paths: dict[Path, int] = {}
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._on_change: OnChange | None = None

    def watch(self, paths: list[Path]) -> None:
        """Register absolute paths to observe."""
        with self._lock:
            for raw in paths:
                path = raw.resolve()
                try:
                    self._paths[path] = path.stat().st_mtime_ns
                except OSError:
                    self._paths[path] = 0

    def add_path(self, path: Path) -> None:
        """Add one path to the watch set."""
        self.watch([path])

    def set_on_change(self, callback: OnChange) -> None:
        """Optional direct callback (used by pipeline worker)."""
        self._on_change = callback

    def start(self) -> None:
        """Start the polling thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="cairn-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop polling and drain the sentinel."""
        self._stop.set()
        with contextlib.suppress(queue.Full):
            self._queue.put_nowait(None)
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def events(self) -> Iterator[WatchEvent]:
        """Blocking iterator over coalesced watch events."""
        while True:
            item = self._queue.get()
            if item is None:
                break
            yield item

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            self._scan_once()
            time.sleep(_POLL_INTERVAL_SEC)

    def _scan_once(self) -> None:
        with self._lock:
            snapshot = list(self._paths.items())
        for path, last_mtime in snapshot:
            try:
                mtime_ns = path.stat().st_mtime_ns
            except OSError:
                continue
            if mtime_ns <= last_mtime:
                continue
            with self._lock:
                self._paths[path] = mtime_ns
            event = WatchEvent(path=path, mtime_ns=mtime_ns)
            self._emit(event)

    def _emit(self, event: WatchEvent) -> None:
        if self._on_change is not None:
            self._on_change(event.path)
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self._coalesce_and_enqueue(event)

    def _coalesce_and_enqueue(self, event: WatchEvent) -> None:
        """When full, drop older events for the same path and keep newest."""
        pending: list[WatchEvent] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except queue.Empty:
                break
            if item is not None:
                pending.append(item)
        by_path = {item.path: item for item in pending}
        by_path[event.path] = event
        for item in by_path.values():
            with contextlib.suppress(queue.Full):
                self._queue.put_nowait(item)
