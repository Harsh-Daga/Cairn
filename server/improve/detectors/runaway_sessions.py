"""Runaway session detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_runaway_sessions(ctx: dict[str, Any]) -> Insight | None:
    runaways = ctx.get("runaway_sessions", []) or []
    if not runaways:
        return None
    top = max(runaways, key=lambda r: r["ratio"])
    return Insight(
        id="runaway-sessions",
        severity="warning",
        title="Runaway sessions",
        body=(
            f"{len(runaways)} {'session' if len(runaways) == 1 else 'sessions'} "
            "exceeded difficulty-adjusted expectations "
            f"(worst: {top['ratio']:.1f}x per-turn growth in {top['run_id'][:12]}). "
            "Context is growing unbounded — split tasks or compact sooner."
        ),
        evidence={"count": len(runaways), "worst_ratio": top["ratio"], "run_id": top["run_id"]},
        savings_estimate=None,
        action="cairn show last",
        difficulty_aware=True,
    )
