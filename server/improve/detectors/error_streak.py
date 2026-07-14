"""Consecutive tool error streaks."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import FixPayload, Insight, LiveDetection


def detect_live_error_streak(spans: list[dict[str, Any]]) -> LiveDetection | None:
    """Find the longest consecutive error streak in ordered live spans."""
    best_count = 0
    best_start = 0
    current_count = 0
    current_start = 0
    for span in spans:
        if span.get("status") == "error":
            if current_count == 0:
                current_start = int(span.get("seq") or 0)
            current_count += 1
            if current_count > best_count:
                best_count = current_count
                best_start = current_start
        else:
            current_count = 0
    if best_count < 4:
        return None
    return LiveDetection(
        pattern="error_streak",
        count=best_count,
        first_seen_seq=best_start,
        advice=(
            f"You've hit {best_count} consecutive tool errors — stop, identify the first root "
            "error, and choose a different diagnostic step."
        ),
        priority=20,
    )


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
