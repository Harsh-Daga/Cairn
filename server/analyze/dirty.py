"""Mark incremental view keys dirty after ingest."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from server.store.repos.views import ViewStateRepo

_TRACE_VIEWS = (
    "usage",
    "regions",
    "waste",
    "fingerprint",
    "difficulty",
    "diagnose",
    "outcomes",
)


def mark_trace_dirty(
    conn: sqlite3.Connection, trace_id: str, *, day: str, project: str
) -> list[str]:
    """Delete view_state rows so schedulers recompute affected keys."""
    dirty: list[str] = []
    for view in _TRACE_VIEWS:
        ViewStateRepo.delete(conn, view, trace_id)
        dirty.append(f"{view}:{trace_id}")
    rollup_key = f"{day}:{project}"
    ViewStateRepo.delete(conn, "rollup", rollup_key)
    dirty.append(f"rollup:{rollup_key}")
    return dirty


def trace_day_key(started_at: str | None) -> str:
    """Derive rollup day from trace timestamp."""
    if not started_at:
        return datetime.now(UTC).strftime("%Y-%m-%d")
    return started_at[:10]
