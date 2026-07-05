"""Deterministic outcome labels."""

from __future__ import annotations

from typing import Any

OutcomeLabel = str  # landed | abandoned | reverted | partial | error_exit | user_aborted


def derive_outcome_label(
    *,
    git_landed: bool,
    tests_passed: int | None,
    tests_failed: int | None,
    status: str,
    events: list[dict[str, Any]],
) -> tuple[OutcomeLabel, str]:
    """Return (outcome_label, label_source). Deterministic only."""
    errors = sum(1 for event in events if event.get("tool_is_error"))
    edits = sum(1 for event in events if event.get("tool_norm_name") == "edit")

    if status in ("user_aborted", "aborted"):
        return "user_aborted", "deterministic"
    if errors >= 3 and not git_landed:
        return "error_exit", "deterministic"
    if git_landed:
        if tests_failed and tests_failed > 0:
            return "partial", "deterministic"
        return "landed", "deterministic"
    if edits >= 2 and not git_landed:
        return "reverted", "deterministic"
    if edits >= 1:
        return "partial", "deterministic"
    if not events or len(events) < 3:
        return "abandoned", "deterministic"
    return "abandoned", "deterministic"
