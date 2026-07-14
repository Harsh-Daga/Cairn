"""Subagent-heavy session detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import FixPayload, Insight

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
        savings_unavailable_reason=(
            "Subagent token share cannot distinguish necessary delegation from waste."
        ),
        fix=FixPayload(
            kind="instruction",
            label="Copy delegation-budget rule",
            value=(
                "Give each subagent one bounded deliverable and stop delegation when its combined "
                "token budget exceeds the main task budget without a usable result."
            ),
        ),
        action=f"cairn show {sid}",
    )
