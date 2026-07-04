"""Diagnostic repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.outcome import Diagnostic
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "diagnostics"
_PK = ("trace_id",)


class DiagnosticRepo:
    """CRUD for the diagnostics table."""

    @staticmethod
    def create(conn: sqlite3.Connection, diagnostic: Diagnostic) -> None:
        insert(conn, _TABLE, diagnostic)

    @staticmethod
    def upsert(conn: sqlite3.Connection, diagnostic: Diagnostic) -> None:
        upsert(conn, _TABLE, diagnostic, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> Diagnostic | None:
        return fetch_one(conn, _TABLE, "trace_id = ?", (trace_id,), Diagnostic)

    @staticmethod
    def list_all(
        conn: sqlite3.Connection, *, limit: int = 100, offset: int = 0
    ) -> list[Diagnostic]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY computed_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
            Diagnostic,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, diagnostic: Diagnostic) -> bool:
        return update(conn, _TABLE, diagnostic, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, trace_id: str) -> bool:
        return delete_where(conn, _TABLE, "trace_id = ?", (trace_id,))
