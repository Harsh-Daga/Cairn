"""Quality regression detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_quality_regression(ctx: dict[str, Any]) -> Insight | None:
    q = ctx.get("quality_regression")
    if not q or not q.get("regressed"):
        return None
    recent = q.get("recent_mean")
    prior = q.get("prior_mean")
    drop = q.get("drop_pct")
    evidence: dict[str, Any] = {
        "recent_mean": recent,
        "prior_mean": prior,
        "drop_pct": drop,
        "recent_n": q.get("recent_n"),
        "prior_n": q.get("prior_n"),
    }
    body = f"Agent Quality Score dropped {drop:.0f}% week-over-week ({prior:.1f} → {recent:.1f})."
    return Insight(
        id="quality-regression",
        severity="warning",
        title="Quality regression",
        body=body,
        evidence=evidence,
        savings_estimate=None,
        action="cairn outcomes",
        difficulty_aware=True,
    )
