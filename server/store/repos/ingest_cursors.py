"""Ingest cursor repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.ingest import IngestCursor
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "ingest_cursors"
_PK = ("source", "stream")


class IngestCursorRepo:
    """CRUD for per-adapter ingest cursors."""

    @staticmethod
    def create(conn: sqlite3.Connection, cursor: IngestCursor) -> None:
        insert(conn, _TABLE, cursor)

    @staticmethod
    def upsert(conn: sqlite3.Connection, cursor: IngestCursor) -> None:
        upsert(conn, _TABLE, cursor, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, source: str, stream: str) -> IngestCursor | None:
        return fetch_one(conn, _TABLE, "source = ? AND stream = ?", (source, stream), IngestCursor)

    @staticmethod
    def list_by_source(conn: sqlite3.Connection, source: str) -> list[IngestCursor]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE source = ? ORDER BY stream ASC",
            (source,),
            IngestCursor,
        )

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> list[IngestCursor]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY source ASC, stream ASC",
            (),
            IngestCursor,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, cursor: IngestCursor) -> bool:
        return update(conn, _TABLE, cursor, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, source: str, stream: str) -> bool:
        return delete_where(conn, _TABLE, "source = ? AND stream = ?", (source, stream))
