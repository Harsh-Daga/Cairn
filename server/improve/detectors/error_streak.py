"""Consecutive tool error streaks."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


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
        action="cairn optimize",
    )
