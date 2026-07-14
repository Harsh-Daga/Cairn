"""Consecutive tool error streaks."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import FixPayload, Insight


def rule_error_streak(ctx: dict[str, Any]) -> Insight | None:
    streak = int(ctx.get("max_error_streak", 0))
    if streak < 4:
        return None
    return Insight(
        id="error-streak",
        severity="error",
        title="Consecutive tool errors",
        body=(
            f"Up to {streak} consecutive tool errors in one session. "
            "The agent may be retrying blindly without changing strategy."
        ),
        evidence={"max_streak": streak},
        savings_estimate=None,
        savings_unavailable_reason="Error spans do not contain a separable dollar cost estimate.",
        fix=FixPayload(
            kind="instruction",
            label="Copy error-stop rule",
            value=(
                "After two consecutive tool errors, stop retrying, explain the failure, and run "
                "a different diagnostic step."
            ),
        ),
        action="cairn optimize",
    )
