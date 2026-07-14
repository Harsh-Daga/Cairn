"""Experiment repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.experiment import Experiment, ExperimentStatus
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_TABLE = "experiments"
_PK = ("experiment_id",)


class ExperimentRepo:
    """CRUD and list queries for the experiments table."""

    @staticmethod
    def create(conn: sqlite3.Connection, experiment: Experiment) -> None:
        insert(conn, _TABLE, experiment)

    @staticmethod
    def upsert(conn: sqlite3.Connection, experiment: Experiment) -> None:
        upsert(conn, _TABLE, experiment, _PK)

    @staticmethod
    def get(conn: sqlite3.Connection, experiment_id: str) -> Experiment | None:
        return fetch_one(conn, _TABLE, "experiment_id = ?", (experiment_id,), Experiment)

    @staticmethod
    def get_active_for_block(
        conn: sqlite3.Connection, target_file: str, block_key: str
    ) -> Experiment | None:
        return fetch_one(
            conn,
            _TABLE,
            "target_file = ? AND block_key = ? AND status IN ('proposed','applied','measuring')",
            (target_file, block_key),
            Experiment,
        )

    @staticmethod
    def list_all(
        conn: sqlite3.Connection,
        *,
        status: ExperimentStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Experiment]:
        if status is None:
            return fetch_all(
                conn,
                f"SELECT * FROM {_TABLE} ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
                Experiment,
            )
        return fetch_all(
            conn,
            f"SELECT * FROM {_TABLE} WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (status, limit, offset),
            Experiment,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, experiment: Experiment) -> bool:
        return update(conn, _TABLE, experiment, _PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, experiment_id: str) -> bool:
        return delete_where(conn, _TABLE, "experiment_id = ?", (experiment_id,))
