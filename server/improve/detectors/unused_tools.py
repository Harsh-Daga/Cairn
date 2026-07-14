"""Unused MCP tool detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import FixPayload, Insight


def rule_unused_tools(ctx: dict[str, Any]) -> Insight | None:
    tools = ctx.get("unused_tools", []) or []
    if not tools:
        return None
    tool = max(tools, key=lambda t: int(t.get("total_turns", 0)))
    name = tool["tool"]
    turns_per_week = int(tool.get("total_turns", 0)) // max(1, 2)  # 14d → 7d
    tokens_per_turn = int(tool.get("tokens_per_turn", 60))
    return Insight(
        id="unused-tools",
        severity="info",
        title=f"Unused MCP tool: {name}",
        body=(
            f"Remove `{name}` — ~{tokens_per_turn} tokens/turn × {turns_per_week} turns/wk "
            f"of schema overhead across {tool.get('sessions', 0)} "
            f"{'session' if tool.get('sessions', 0) == 1 else 'sessions'}."
        ),
        evidence=tool,
        savings_estimate=None,
        savings_unavailable_reason=(
            "Schema tokens are measured, but their provider-specific price is unavailable."
        ),
        fix=FixPayload(
            kind="settings",
            label=f"Disable {name}",
            value=f"Remove `{name}` from the agent's enabled MCP tools until a task requires it.",
        ),
        action="cairn optimize",
        difficulty_aware=True,
    )
