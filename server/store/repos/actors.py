"""Actor repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.workspace import Actor, ActorKind
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "actors"
_PK = ("actor_id",)


class ActorRepo:
    """CRUD for the actors table."""

    @staticmethod
    def create(conn: sqlite3.Connection, actor: Actor) -> None:
        insert(conn, _TABLE, actor)

    @staticmethod
    def upsert(conn: sqlite3.Connection, actor: Actor) -> None:
        upsert(conn, _TABLE, actor, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, actor_id: str) -> Actor | None:
        return fetch_one(conn, _TABLE, "actor_id = ?", (actor_id,), Actor)

    @staticmethod
    def get_by_identity(
        conn: sqlite3.Connection,
        kind: ActorKind,
        identity_hint: str,
    ) -> Actor | None:
        return fetch_one(
            conn,
            _TABLE,
            "kind = ? AND identity_hint = ?",
            (kind, identity_hint),
            Actor,
        )

    @staticmethod
    def list_all(conn: sqlite3.Connection) -> list[Actor]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY display_name ASC",
            (),
            Actor,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, actor: Actor) -> bool:
        return update(conn, _TABLE, actor, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, actor_id: str) -> bool:
        return delete_where(conn, _TABLE, "actor_id = ?", (actor_id,))
