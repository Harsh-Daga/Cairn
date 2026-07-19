"""Guard event repository."""

from __future__ import annotations

import sqlite3

from server.models.guard_event import GuardEvent
from server.store.pagination import bounded_page
from server.store.repos._crud import fetch_all, fetch_one, upsert

_TABLE = "guard_events"
_PK = ("event_id",)


class GuardEventRepo:
    @staticmethod
    def upsert(conn: sqlite3.Connection, event: GuardEvent) -> None:
        upsert(conn, _TABLE, event, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, event_id: str) -> GuardEvent | None:
        return fetch_one(conn, _TABLE, "event_id = ?", (event_id,), GuardEvent)

    @staticmethod
    def list_for_workspace(
        conn: sqlite3.Connection,
        workspace_id: str,
        *,
        since: str | None = None,
        until: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[GuardEvent]:
        limit, offset = bounded_page(limit, offset)
        clauses = ["workspace_id = ?"]
        params: list[object] = [workspace_id]
        if since:
            clauses.append("occurred_at >= ?")
            params.append(since)
        if until:
            clauses.append("occurred_at < ?")
            params.append(until)
        where = " AND ".join(clauses)
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE {where} "
            f"ORDER BY occurred_at DESC, event_id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
            GuardEvent,
        )

    @staticmethod
    def count_for_workspace(
        conn: sqlite3.Connection,
        workspace_id: str,
        *,
        since: str | None = None,
        until: str | None = None,
    ) -> int:
        clauses = ["workspace_id = ?"]
        params: list[object] = [workspace_id]
        if since:
            clauses.append("occurred_at >= ?")
            params.append(since)
        if until:
            clauses.append("occurred_at < ?")
            params.append(until)
        where = " AND ".join(clauses)
        row = conn.execute(
            f"SELECT COUNT(*) AS n FROM {_TABLE} WHERE {where}",
            params,
        ).fetchone()
        return int(row["n"]) if row else 0
