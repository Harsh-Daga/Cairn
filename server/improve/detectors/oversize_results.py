"""Oversized tool result detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight, _cap_savings, _data_note, _weekly_spend


def rule_oversize_tool_results(ctx: dict[str, Any]) -> Insight | None:
    waste = int(ctx.get("oversize_result_tokens", 0))
    if waste <= 20_000:
        return None
    total_tokens = int(ctx.get("total_tokens", 0))
    total_cost = float(ctx.get("total_cost", 0))
    days = int(ctx.get("days", 14))
    has_cost = ctx.get("has_cost_sessions", 0) > 0
    savings: float | None = None
    evidence: dict[str, Any] = {"waste_tokens": waste}
    if has_cost and total_tokens > 0 and total_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = (waste / total_tokens) * weekly_spend * 0.4
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(_data_note("no cost data: savings estimate unavailable (div0 guard)"))
    return Insight(
        id="oversize-tool-results",
        severity="info",
        title="Oversized tool results",
        body=(
            f"{waste:,} tokens went to oversized tool results. "
            "Use more targeted file reads and narrower grep patterns."
        ),
        evidence=evidence,
        savings_estimate=savings,
        action="cairn optimize",
    )
