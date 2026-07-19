"""Daily rollup repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.rollup import RollupDaily
from server.store.pagination import bounded_page
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "rollup_daily"
_PK = ("day", "workspace_id", "project", "source", "model")


class RollupRepo:
    """CRUD for the rollup_daily table."""

    @staticmethod
    def create(conn: sqlite3.Connection, rollup: RollupDaily) -> None:
        insert(conn, _TABLE, rollup)

    @staticmethod
    def upsert(conn: sqlite3.Connection, rollup: RollupDaily) -> None:
        upsert(conn, _TABLE, rollup, _PK)

    @staticmethod
    def get(
        conn: sqlite3.Connection,
        day: str,
        workspace_id: str,
        project: str,
        source: str,
        model: str = "",
    ) -> RollupDaily | None:
        return fetch_one(
            conn,
            _TABLE,
            "day = ? AND workspace_id = ? AND project = ? AND source = ? AND model = ?",
            (day, workspace_id, project, source, model),
            RollupDaily,
        )

    @staticmethod
    def list_by_workspace(
        conn: sqlite3.Connection,
        workspace_id: str,
        *,
        days: int | None = None,
        start: str | None = None,
        end: str | None = None,
        limit: int = 365,
    ) -> list[RollupDaily]:
        limit, _ = bounded_page(limit)
        if start is not None or end is not None:
            clauses = ["workspace_id = ?"]
            params: list[object] = [workspace_id]
            if start is not None:
                clauses.append("day >= ?")
                params.append(start)
            if end is not None:
                clauses.append("day < ?")
                params.append(end)
            params.append(limit)
            return fetch_all(
                conn,
                f"SELECT * FROM {_TABLE} WHERE {' AND '.join(clauses)} ORDER BY day DESC LIMIT ?",
                tuple(params),
                RollupDaily,
            )
        if days is None:
            return fetch_all(
                conn,
                f"SELECT * FROM {_TABLE} WHERE workspace_id = ? ORDER BY day DESC LIMIT ?",
                (workspace_id, limit),
                RollupDaily,
            )
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE workspace_id = ? AND day >= date('now', ?) "
            "ORDER BY day DESC LIMIT ?",
            (workspace_id, f"-{days} days", limit),
            RollupDaily,
        )

    @staticmethod
    def list_by_day(conn: sqlite3.Connection, day: str) -> list[RollupDaily]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE day = ? ORDER BY project ASC, source ASC",
            (day,),
            RollupDaily,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, rollup: RollupDaily) -> bool:
        return update(conn, _TABLE, rollup, _PK)

    @staticmethod
    def delete(
        conn: sqlite3.Connection,
        day: str,
        workspace_id: str,
        project: str,
        source: str,
        model: str = "",
    ) -> bool:
        return delete_where(
            conn,
            _TABLE,
            "day = ? AND workspace_id = ? AND project = ? AND source = ? AND model = ?",
            (day, workspace_id, project, source, model),
        )
