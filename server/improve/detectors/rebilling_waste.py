"""Re-billed stale context token detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import (
    FixPayload,
    Insight,
    _cap_savings,
    _data_note,
    _weekly_spend,
)


def rule_rebilling_waste(ctx: dict[str, Any]) -> Insight | None:
    rebilled = int(ctx.get("rebilling_tokens_14d", 0))
    if rebilled <= 50_000:
        return None
    days = max(1, int(ctx.get("days", 14)))
    total_cost = float(ctx.get("total_cost", 0))
    has_cost = ctx.get("has_cost_sessions", 0) > 0
    rebilling_cost = float(ctx.get("rebilling_cost_14d", 0.0) or 0.0)
    savings: float | None = None
    evidence: dict[str, Any] = {
        "rebilled_tokens": rebilled,
        "rebilled_cost_usd": rebilling_cost or None,
    }
    if has_cost and total_cost > 0 and rebilling_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = rebilling_cost * (7.0 / days) * 0.6
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(
            _data_note("no input price for re-billed tokens: savings null (div0 guard)")
        )
    return Insight(
        id="rebilling-waste",
        severity="info",
        title="Re-billed stale context tokens",
        body=(
            f"{rebilled:,} stale tool-result tokens were re-billed across sessions in the last "
            f"{days} days. Clearing consumed tool results from the window stops the re-billing."
        ),
        evidence=evidence,
        savings_estimate=savings,
        savings_unavailable_reason=(
            "No reliable input-token price is available for re-billed context."
        ),
        fix=FixPayload(
            kind="instruction",
            label="Copy context-trimming rule",
            value=(
                "Summarize consumed tool results, remove their raw output from working context, "
                "and re-read only if the source changes."
            ),
        ),
        action="cairn profile",
        difficulty_aware=True,
    )
