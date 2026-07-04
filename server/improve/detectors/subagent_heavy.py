"""Subagent-heavy session detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight

# Subagent/sidechain lanes above this share of run tokens trigger the insight.
SUBAGENT_HEAVY_THRESHOLD = 0.60


def rule_subagent_heavy(ctx: dict[str, Any]) -> Insight | None:
    hit = ctx.get("subagent_heavy")
    if not hit:
        return None
    share_pct = float(hit.get("share_pct", 0))
    run_id = str(hit.get("run_id", ""))
    sid = run_id[:12] if run_id else "session"
    return Insight(
        id="subagent-heavy",
        severity="warning",
        title="Subagent-heavy session",
        body=(
            f"Subagents consumed {share_pct:.0f}% of tokens in session {sid} "
            f"without a success outcome — review delegation before retrying."
        ),
        evidence={
            "run_id": run_id,
            "share_pct": share_pct,
            "subagent_tokens": hit.get("subagent_tokens"),
        },
        savings_estimate=None,
        action=f"cairn show {sid}",
    )
