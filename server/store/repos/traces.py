"""Trace repository (Phase 1)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from server.models.trace import Trace
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "traces"
_PK = ("trace_id",)


@dataclass(frozen=True, slots=True)
class TraceListFilters:
    """Filters for GET /api/traces."""

    days: int | None = None
    source: str | None = None
    project: str | None = None
    actor: str | None = None
    agent: str | None = None
    q: str | None = None
    sort: str = "recent"
    workspace_id: str | None = None
    limit: int = 50
    offset: int = 0


def _days_cutoff(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _list_where(filters: TraceListFilters) -> tuple[str, list[object]]:
    clauses: list[str] = []
    params: list[object] = []
    if filters.workspace_id is not None:
        clauses.append("workspace_id = ?")
        params.append(filters.workspace_id)
    if filters.days is not None:
        clauses.append("(started_at IS NULL OR started_at >= ?)")
        params.append(_days_cutoff(filters.days))
    if filters.source is not None:
        clauses.append("source = ?")
        params.append(filters.source)
    if filters.project is not None:
        clauses.append("project = ?")
        params.append(filters.project)
    if filters.actor is not None:
        clauses.append("actor_id = ?")
        params.append(filters.actor)
    if filters.agent is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM spans s "
            "WHERE s.trace_id = traces.trace_id AND s.agent_id = ?)"
        )
        params.append(filters.agent)
    if filters.q is not None and filters.q.strip():
        clauses.append(
            "(LOWER(COALESCE(title, '')) LIKE ? "
            "OR LOWER(trace_id) LIKE ? "
            "OR LOWER(COALESCE(project, '')) LIKE ?)"
        )
        needle = f"%{filters.q.strip().lower()}%"
        params.extend((needle, needle, needle))
    where = " AND ".join(clauses) if clauses else "1 = 1"
    return where, params


class TraceRepo:
    """CRUD and list queries for the traces table."""

    @staticmethod
    def create(conn: sqlite3.Connection, trace: Trace) -> None:
        insert(conn, _TABLE, trace)

    @staticmethod
    def upsert(conn: sqlite3.Connection, trace: Trace) -> None:
        upsert(conn, _TABLE, trace, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> Trace | None:
        return fetch_one(conn, _TABLE, "trace_id = ?", (trace_id,), Trace)

    @staticmethod
    def get_by_external(
        conn: sqlite3.Connection,
        source: str,
        external_id: str,
    ) -> Trace | None:
        return fetch_one(
            conn,
            _TABLE,
            "source = ? AND external_id = ?",
            (source, external_id),
            Trace,
        )

    @staticmethod
    def list(conn: sqlite3.Connection, filters: TraceListFilters) -> list[Trace]:
        where, params = _list_where(filters)
        order_by = {
            "cost": "cost DESC, started_at DESC, trace_id DESC",
            "waste": "waste_tokens DESC, started_at DESC, trace_id DESC",
        }.get(filters.sort, "started_at DESC, trace_id DESC")
        sql = (
            f"SELECT * FROM {_TABLE} WHERE {where} "
            f"ORDER BY {order_by} "
            "LIMIT ? OFFSET ?"
        )
        return fetch_all(conn, sql, (*params, filters.limit, filters.offset), Trace)

    @staticmethod
    def count(conn: sqlite3.Connection, filters: TraceListFilters) -> int:
        where, params = _list_where(filters)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {_TABLE} WHERE {where}",
            params,
        ).fetchone()
        return int(row["n"]) if row is not None else 0

    @staticmethod
    def update(conn: sqlite3.Connection, trace: Trace) -> bool:
        return update(conn, _TABLE, trace, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, trace_id: str) -> bool:
        return delete_where(conn, _TABLE, "trace_id = ?", (trace_id,))
