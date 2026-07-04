"""View state repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.evidence import ViewState
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "view_state"
_PK = ("view", "key")


class ViewStateRepo:
    """CRUD for the view_state incremental maintenance ledger."""

    @staticmethod
    def create(conn: sqlite3.Connection, entry: ViewState) -> None:
        insert(conn, _TABLE, entry)

    @staticmethod
    def upsert(conn: sqlite3.Connection, entry: ViewState) -> None:
        upsert(conn, _TABLE, entry, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, view: str, key: str) -> ViewState | None:
        return fetch_one(conn, _TABLE, "view = ? AND key = ?", (view, key), ViewState)

    @staticmethod
    def list_by_view(conn: sqlite3.Connection, view: str) -> list[ViewState]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE view = ? ORDER BY computed_at DESC",
            (view,),
            ViewState,
        )

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> list[ViewState]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY view ASC, key ASC",
            (),
            ViewState,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, entry: ViewState) -> bool:
        return update(conn, _TABLE, entry, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, view: str, key: str) -> bool:
        return delete_where(conn, _TABLE, "view = ? AND key = ?", (view, key))

    @staticmethod
    def delete_by_view(conn: sqlite3.Connection, view: str) -> int:
        cur = conn.execute(f"DELETE FROM {_TABLE} WHERE view = ?", (view,))
        return cur.rowcount
