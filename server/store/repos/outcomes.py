"""Outcome repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.outcome import Outcome
from server.store.pagination import bounded_page
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "outcomes"
_PK = ("trace_id",)


class OutcomeRepo:
    """CRUD for the outcomes table."""

    @staticmethod
    def create(conn: sqlite3.Connection, outcome: Outcome) -> None:
        insert(conn, _TABLE, outcome)

    @staticmethod
    def upsert(conn: sqlite3.Connection, outcome: Outcome) -> None:
        upsert(conn, _TABLE, outcome, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> Outcome | None:
        return fetch_one(conn, _TABLE, "trace_id = ?", (trace_id,), Outcome)

    @staticmethod
    def list_all(conn: sqlite3.Connection, *, limit: int = 100, offset: int = 0) -> list[Outcome]:
        limit, offset = bounded_page(limit, offset)
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY captured_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
            Outcome,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, outcome: Outcome) -> bool:
        return update(conn, _TABLE, outcome, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, trace_id: str) -> bool:
        return delete_where(conn, _TABLE, "trace_id = ?", (trace_id,))
