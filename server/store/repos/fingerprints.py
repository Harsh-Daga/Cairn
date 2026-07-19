"""Fingerprint repository (Phase 1)."""

from __future__ import annotations

import sqlite3

from server.models.fingerprint import Fingerprint, FingerprintBaseline
from server.store.pagination import bounded_page
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_FINGERPRINTS = "fingerprints"
_BASELINES = "fingerprint_baselines"
_FP_PK = ("trace_id",)
_BL_PK = ("project", "model", "week")


class FingerprintRepo:
    """CRUD for fingerprints and fingerprint_baselines tables."""

    @staticmethod
    def create(conn: sqlite3.Connection, fingerprint: Fingerprint) -> None:
        insert(conn, _FINGERPRINTS, fingerprint)

    @staticmethod
    def upsert(conn: sqlite3.Connection, fingerprint: Fingerprint) -> None:
        upsert(conn, _FINGERPRINTS, fingerprint, _FP_PK)

    @staticmethod
    def get(conn: sqlite3.Connection, trace_id: str) -> Fingerprint | None:
        return fetch_one(conn, _FINGERPRINTS, "trace_id = ?", (trace_id,), Fingerprint)

    @staticmethod
    def list_by_project(
        conn: sqlite3.Connection,
        project: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Fingerprint]:
        limit, offset = bounded_page(limit, offset)
        return fetch_all(
            conn,
            f"SELECT * FROM {_FINGERPRINTS} WHERE project = ? ORDER BY ts DESC LIMIT ? OFFSET ?",
            (project, limit, offset),
            Fingerprint,
        )

    @staticmethod
    def update(conn: sqlite3.Connection, fingerprint: Fingerprint) -> bool:
        return update(conn, _FINGERPRINTS, fingerprint, _FP_PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, trace_id: str) -> bool:
        return delete_where(conn, _FINGERPRINTS, "trace_id = ?", (trace_id,))

    @staticmethod
    def create_baseline(conn: sqlite3.Connection, baseline: FingerprintBaseline) -> None:
        insert(conn, _BASELINES, baseline)

    @staticmethod
    def upsert_baseline(conn: sqlite3.Connection, baseline: FingerprintBaseline) -> None:
        upsert(conn, _BASELINES, baseline, _BL_PK)

    @staticmethod
    def get_baseline(
        conn: sqlite3.Connection,
        project: str,
        model: str,
        week: str,
    ) -> FingerprintBaseline | None:
        return fetch_one(
            conn,
            _BASELINES,
            "project = ? AND model = ? AND week = ?",
            (project, model, week),
            FingerprintBaseline,
        )

    @staticmethod
    def list_baselines(
        conn: sqlite3.Connection,
        *,
        project: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[FingerprintBaseline]:
        limit, offset = bounded_page(limit, offset)
        if project is None:
            return fetch_all(
                conn,
                f"SELECT * FROM {_BASELINES} ORDER BY week DESC LIMIT ? OFFSET ?",
                (limit, offset),
                FingerprintBaseline,
            )
        return fetch_all(
            conn,
            f"SELECT * FROM {_BASELINES} WHERE project = ? ORDER BY week DESC LIMIT ? OFFSET ?",
            (project, limit, offset),
            FingerprintBaseline,
        )

    @staticmethod
    def update_baseline(conn: sqlite3.Connection, baseline: FingerprintBaseline) -> bool:
        return update(conn, _BASELINES, baseline, _BL_PK)

    @staticmethod
    def delete_baseline(
        conn: sqlite3.Connection,
        project: str,
        model: str,
        week: str,
    ) -> bool:
        return delete_where(
            conn,
            _BASELINES,
            "project = ? AND model = ? AND week = ?",
            (project, model, week),
        )
