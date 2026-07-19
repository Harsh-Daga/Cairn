"""Data quality repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.data_quality import DataQuality
from server.store.pagination import bounded_page
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "data_quality"
_PK = ("trace_id",)


class DataQualityRepo:
    """CRUD for the data_quality table."""

    @staticmethod
    def create(conn: sqlite3.Connection, quality: DataQuality) -> None:
        insert(conn, _TABLE, quality)

    @staticmethod
    def upsert(conn: sqlite3.Connection, quality: DataQuality) -> None:
        upsert(conn, _TABLE, quality, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> DataQuality | None:
        return fetch_one(conn, _TABLE, "trace_id = ?", (trace_id,), DataQuality)

    @staticmethod
    def list_all(
        conn: sqlite3.Connection,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[DataQuality]:
        limit, offset = bounded_page(limit, offset)
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY computed_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
            DataQuality,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, quality: DataQuality) -> bool:
        return update(conn, _TABLE, quality, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, trace_id: str) -> bool:
        return delete_where(conn, _TABLE, "trace_id = ?", (trace_id,))
