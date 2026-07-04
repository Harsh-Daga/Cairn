"""Context-region repository (Phase 4)."""

from __future__ import annotations

import sqlite3

from server.models.context_region import ContextRegion

_TABLE = "context_regions"


class ContextRegionRepo:
    """CRUD-like operations for per-span context regions."""

    @staticmethod
    def delete_by_trace(conn: sqlite3.Connection, trace_id: str) -> int:
        cur = conn.execute(
            f"DELETE FROM {_TABLE} WHERE span_id IN (SELECT span_id FROM spans WHERE trace_id = ?)",
            (trace_id,),
        )
        return cur.rowcount

    @staticmethod
    def upsert_many(conn: sqlite3.Connection, rows: list[ContextRegion]) -> None:
        if not rows:
            return
        fields = ContextRegion.INSERT_FIELDS
        placeholders = ", ".join("?" * len(fields))
        updates = ", ".join(
            f"{field} = excluded.{field}" for field in fields if field not in {"span_id", "region"}
        )
        sql = (
            f"INSERT INTO {_TABLE} ({', '.join(fields)}) VALUES ({placeholders}) "
            f"ON CONFLICT(span_id, region) DO UPDATE SET {updates}"
        )
        conn.executemany(sql, [row.to_row() for row in rows])

    @staticmethod
    def list_by_trace(conn: sqlite3.Connection, trace_id: str) -> list[ContextRegion]:
        result = conn.execute(
            f"""
            SELECT cr.*
            FROM {_TABLE} cr
            JOIN spans s ON s.span_id = cr.span_id
            WHERE s.trace_id = ?
            ORDER BY s.seq ASC, cr.region ASC
            """,
            (trace_id,),
        ).fetchall()
        return [ContextRegion.from_row(row) for row in result]
