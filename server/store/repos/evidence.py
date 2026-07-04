"""Evidence repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.evidence import Evidence
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "evidence"
_PK = ("evidence_id",)


class EvidenceRepo:
    """CRUD for the evidence provenance table."""

    @staticmethod
    def create(conn: sqlite3.Connection, evidence: Evidence) -> None:
        insert(conn, _TABLE, evidence)

    @staticmethod
    def upsert(conn: sqlite3.Connection, evidence: Evidence) -> None:
        upsert(conn, _TABLE, evidence, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, evidence_id: str) -> Evidence | None:
        return fetch_one(conn, _TABLE, "evidence_id = ?", (evidence_id,), Evidence)

    @staticmethod
    def list_by_producer(
        conn: sqlite3.Connection,
        producer: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Evidence]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE producer = ? ORDER BY produced_at DESC LIMIT ? OFFSET ?",
            (producer, limit, offset),
            Evidence,
        )

    @staticmethod
    def list_all(conn: sqlite3.Connection, *, limit: int = 100, offset: int = 0) -> list[Evidence]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} ORDER BY produced_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
            Evidence,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, evidence: Evidence) -> bool:
        return update(conn, _TABLE, evidence, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, evidence_id: str) -> bool:
        return delete_where(conn, _TABLE, "evidence_id = ?", (evidence_id,))
