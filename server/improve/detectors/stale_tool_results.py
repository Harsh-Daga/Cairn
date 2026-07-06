"""Stale tool results still in context after last reference."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight, _cap_savings


def rule_stale_tool_results(ctx: dict[str, Any]) -> Insight | None:
    events = int(ctx.get("stale_tool_result_events", 0))
    tokens = int(ctx.get("stale_tool_result_tokens", 0))
    if events < 3:
        return None
    return Insight(
        id="stale-tool-results",
        severity="warning",
        title="Stale tool results in context",
        body=(
            f"{events} tool results stayed in the window after they were last referenced "
            f"({tokens:,} waste tokens). Trim or summarize old tool output."
        ),
        evidence={"events": events, "tokens": tokens},
        savings_estimate=_cap_savings(tokens),
        action="cairn optimize",
    )
