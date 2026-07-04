"""Workspace repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.workspace import Workspace
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "workspaces"
_PK = ("workspace_id",)


class WorkspaceRepo:
    """CRUD for the workspaces table."""

    @staticmethod
    def create(conn: sqlite3.Connection, workspace: Workspace) -> None:
        insert(conn, _TABLE, workspace)

    @staticmethod
    def upsert(conn: sqlite3.Connection, workspace: Workspace) -> None:
        upsert(conn, _TABLE, workspace, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, workspace_id: str) -> Workspace | None:
        return fetch_one(conn, _TABLE, "workspace_id = ?", (workspace_id,), Workspace)

    @staticmethod
    def get_by_root_path(conn: sqlite3.Connection, root_path: str) -> Workspace | None:
        return fetch_one(conn, _TABLE, "root_path = ?", (root_path,), Workspace)

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> list[Workspace]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY created_at ASC",
            (),
            Workspace,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, workspace: Workspace) -> bool:
        return update(conn, _TABLE, workspace, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, workspace_id: str) -> bool:
        return delete_where(conn, _TABLE, "workspace_id = ?", (workspace_id,))
