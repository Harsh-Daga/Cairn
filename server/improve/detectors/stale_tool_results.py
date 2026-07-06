"""Stale tool results still in context after last reference."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight, _cap_savings, _data_note, _weekly_spend


def rule_stale_tool_results(ctx: dict[str, Any]) -> Insight | None:
    events = int(ctx.get("stale_tool_result_events", 0))
    tokens = int(ctx.get("stale_tool_result_tokens", 0))
    if events < 3:
        return None
    total_tokens = int(ctx.get("total_tokens", 0))
    total_cost = float(ctx.get("total_cost", 0))
    days = int(ctx.get("days", 14))
    savings: float | None = None
    evidence: dict[str, Any] = {"events": events, "tokens": tokens}
    if ctx.get("has_cost_sessions", 0) > 0 and total_tokens > 0 and total_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = (tokens / total_tokens) * weekly_spend * 0.5
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(_data_note("no cost data: savings estimate unavailable (div0 guard)"))
    return Insight(
        id="stale-tool-results",
        severity="warning",
        title="Stale tool results in context",
        body=(
            f"{events} tool results stayed in the window after they were last referenced "
            f"({tokens:,} waste tokens). Trim or summarize old tool output."
        ),
        evidence=evidence,
        savings_estimate=savings,
        action="cairn optimize",
    )
