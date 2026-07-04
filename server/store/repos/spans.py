"""Span repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.span import Span
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "spans"
_PK = ("span_id",)


class SpanRepo:
    """CRUD for the spans table."""

    @staticmethod
    def create(conn: sqlite3.Connection, span: Span) -> None:
        insert(conn, _TABLE, span)

    @staticmethod
    def upsert(conn: sqlite3.Connection, span: Span) -> None:
        upsert(conn, _TABLE, span, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, span_id: str) -> Span | None:
        return fetch_one(conn, _TABLE, "span_id = ?", (span_id,), Span)

    @staticmethod
    def list_by_trace(conn: sqlite3.Connection, trace_id: str) -> list[Span]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE trace_id = ? ORDER BY seq ASC",
            (trace_id,),
            Span,
        )

    @staticmethod
    def list_children(conn: sqlite3.Connection, parent_span_id: str) -> list[Span]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE parent_span_id = ? ORDER BY seq ASC",
            (parent_span_id,),
            Span,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, span: Span) -> bool:
        return update(conn, _TABLE, span, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, span_id: str) -> bool:
        return delete_where(conn, _TABLE, "span_id = ?", (span_id,))

    @staticmethod
    def delete_by_trace(conn: sqlite3.Connection, trace_id: str) -> int:
        cur = conn.execute(f"DELETE FROM {_TABLE} WHERE trace_id = ?", (trace_id,))
        return cur.rowcount
