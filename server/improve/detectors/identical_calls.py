"""Duplicate tool call detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight, _cap_savings, _data_note, _weekly_spend


def rule_identical_tool_calls(ctx: dict[str, Any]) -> Insight | None:
    waste = int(ctx.get("identical_call_tokens", 0))
    if waste <= 10_000:
        return None
    total_tokens = int(ctx.get("total_tokens", 0))
    total_cost = float(ctx.get("total_cost", 0))
    days = int(ctx.get("days", 14))
    has_cost = ctx.get("has_cost_sessions", 0) > 0
    savings: float | None = None
    evidence: dict[str, Any] = {
        "waste_tokens": waste,
        "events": int(ctx.get("identical_call_events", 0)),
    }
    if has_cost and total_tokens > 0 and total_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = (waste / total_tokens) * weekly_spend * 0.5
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(_data_note("no cost data: savings estimate unavailable (div0 guard)"))
    return Insight(
        id="identical-tool-calls",
        severity="warning",
        title="Duplicate tool calls",
        body=(
            f"{evidence['events']} duplicate tool calls detected in last {days} days. "
            "Agent is repeating reads/searches it already has results for."
        ),
        evidence=evidence,
        savings_estimate=savings,
        action="cairn optimize",
    )
