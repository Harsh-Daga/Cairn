"""SQLite Action Cache (R2, R14) — uses a Ledger-owned connection."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime


class ActionCache:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, action_key: str) -> str | None:
        row = self._conn.execute(
            "SELECT output_hash FROM action_cache WHERE action_key = ?",
            (action_key,),
        ).fetchone()
        return row[0] if row else None

    def put(self, action_key: str, output_hash: str, *, kind: str, model: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            """
            INSERT INTO action_cache (
              action_key, output_hash, kind, created_at, last_used_at, model
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(action_key) DO UPDATE SET
              output_hash = excluded.output_hash,
              last_used_at = excluded.last_used_at
            """,
            (action_key, output_hash, kind, now, now, model),
        )
        self._conn.commit()

    def touch(self, action_key: str) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE action_cache SET last_used_at = ? WHERE action_key = ?",
            (now, action_key),
        )
        self._conn.commit()

    def delete(self, action_key: str) -> None:
        self._conn.execute("DELETE FROM action_cache WHERE action_key = ?", (action_key,))
        self._conn.commit()
