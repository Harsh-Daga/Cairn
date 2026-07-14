"""Insight evaluation engine — run detectors and persist results."""

from __future__ import annotations

import sqlite3

from server.improve.context import build_context
from server.improve.detectors._types import validate_insight_contract
from server.improve.detectors.rules import ALL_RULES
from server.improve.evidence import draft_from_legacy
from server.improve.lifecycle import mark_stale_fixed, upsert_insight
from server.models.insight import Insight


def evaluate(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 14,
) -> list[Insight]:
    """Evaluate all detector rules and upsert insights."""
    ctx = build_context(conn, workspace_id=workspace_id, days=days)
    drafts = []
    for rule in ALL_RULES:
        result = rule(ctx)
        if result is not None:
            validate_insight_contract(result)
            drafts.append(draft_from_legacy(result.id, result))

    insights: list[Insight] = []
    active_fps = {d.fingerprint for d in drafts}
    for draft in drafts:
        insights.append(upsert_insight(conn, draft))
    mark_stale_fixed(conn, active_fps)

    severity_order = {"error": 0, "warning": 1, "info": 2, "suggestion": 3}
    insights.sort(key=lambda i: (severity_order.get(i.severity, 4), -(i.savings_estimate or 0)))
    return insights
