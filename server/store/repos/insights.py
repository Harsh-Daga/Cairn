"""Insight repository (Phase 1)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from server.models.insight import Insight, InsightLifecycle, InsightState
from server.store.repos._crud import delete_where, fetch_all, fetch_one, insert, update, upsert

_INSIGHTS = "insights"
_STATES = "insight_states"
_INSIGHT_PK = ("insight_id",)
_STATE_PK = ("insight_id",)


@dataclass(frozen=True, slots=True)
class InsightWithState:
    """Insight joined with lifecycle state."""

    insight: Insight
    state: InsightState


class InsightRepo:
    """CRUD for insights and insight_states tables."""

    @staticmethod
    def create(conn: sqlite3.Connection, insight: Insight) -> None:
        insert(conn, _INSIGHTS, insight)

    @staticmethod
    def upsert(conn: sqlite3.Connection, insight: Insight) -> None:
        upsert(conn, _INSIGHTS, insight, _INSIGHT_PK)

    @staticmethod
    def get(conn: sqlite3.Connection, insight_id: str) -> Insight | None:
        return fetch_one(conn, _INSIGHTS, "insight_id = ?", (insight_id,), Insight)

    @staticmethod
    def get_by_fingerprint(conn: sqlite3.Connection, fingerprint: str) -> Insight | None:
        return fetch_one(conn, _INSIGHTS, "fingerprint = ?", (fingerprint,), Insight)

    @staticmethod
    def list_all(
        conn: sqlite3.Connection,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Insight]:
        return fetch_all(
            conn,
            f"SELECT * FROM {_INSIGHTS} ORDER BY last_seen_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
            Insight,
        )

    @staticmethod
    def list_by_state(
        conn: sqlite3.Connection,
        state: InsightLifecycle | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[InsightWithState]:
        if state is None:
            rows = conn.execute(
                f"""
                SELECT i.*, s.insight_id AS state_insight_id, s.state, s.changed_at, s.changed_by
                FROM {_INSIGHTS} i
                LEFT JOIN {_STATES} s ON i.insight_id = s.insight_id
                ORDER BY i.last_seen_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                f"""
                SELECT i.*, s.insight_id AS state_insight_id, s.state, s.changed_at, s.changed_by
                FROM {_INSIGHTS} i
                LEFT JOIN {_STATES} s ON i.insight_id = s.insight_id
                WHERE COALESCE(s.state, 'new') = ?
                ORDER BY i.last_seen_at DESC
                LIMIT ? OFFSET ?
                """,
                (state, limit, offset),
            ).fetchall()
        return [_insight_with_state_from_row(row) for row in rows]

    @staticmethod
    def count_by_state(conn: sqlite3.Connection, state: InsightLifecycle | None = None) -> int:
        if state is None:
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {_INSIGHTS}").fetchone()
        else:
            row = conn.execute(
                f"""
                SELECT COUNT(*) AS n
                FROM {_INSIGHTS} i
                LEFT JOIN {_STATES} s ON i.insight_id = s.insight_id
                WHERE COALESCE(s.state, 'new') = ?
                """,
                (state,),
            ).fetchone()
        return int(row["n"] or 0) if row is not None else 0

    @staticmethod
    def update(conn: sqlite3.Connection, insight: Insight) -> bool:
        return update(conn, _INSIGHTS, insight, _INSIGHT_PK)

    @staticmethod
    def delete(conn: sqlite3.Connection, insight_id: str) -> bool:
        delete_where(conn, _STATES, "insight_id = ?", (insight_id,))
        return delete_where(conn, _INSIGHTS, "insight_id = ?", (insight_id,))

    @staticmethod
    def get_state(conn: sqlite3.Connection, insight_id: str) -> InsightState | None:
        return fetch_one(conn, _STATES, "insight_id = ?", (insight_id,), InsightState)

    @staticmethod
    def set_state(conn: sqlite3.Connection, state: InsightState) -> None:
        upsert(conn, _STATES, state, _STATE_PK)

    @staticmethod
    def create_state(conn: sqlite3.Connection, state: InsightState) -> None:
        insert(conn, _STATES, state)

    @staticmethod
    def update_state(conn: sqlite3.Connection, state: InsightState) -> bool:
        return update(conn, _STATES, state, _STATE_PK)

    @staticmethod
    def delete_state(conn: sqlite3.Connection, insight_id: str) -> bool:
        return delete_where(conn, _STATES, "insight_id = ?", (insight_id,))


def _insight_with_state_from_row(row: sqlite3.Row) -> InsightWithState:
    insight = Insight.from_row(row)
    raw_state = row["state"]
    lifecycle: InsightLifecycle = "new" if raw_state is None else str(raw_state)  # type: ignore[assignment]
    changed_at = row["changed_at"]
    state = InsightState(
        insight_id=insight.insight_id,
        state=lifecycle,
        changed_at=str(changed_at) if changed_at is not None else insight.created_at,
        changed_by=None if row["changed_by"] is None else str(row["changed_by"]),
    )
    return InsightWithState(insight=insight, state=state)
