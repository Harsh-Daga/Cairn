"""Failure taxonomy classification."""

from __future__ import annotations

from typing import Any


def classify_failure(
    events: list[dict[str, Any]],
    *,
    outcome_label: str | None,
    failure_signature: str | None,
) -> tuple[str | None, str | None]:
    """Deterministic primary + secondary categories."""
    if outcome_label in {"landed", None}:
        return None, None

    reads = sum(1 for event in events if event.get("tool_norm_name") in {"read", "search"})
    edits = sum(1 for event in events if event.get("tool_norm_name") == "edit")
    errors = sum(1 for event in events if event.get("tool_is_error"))
    bash = sum(1 for event in events if event.get("tool_norm_name") == "bash")
    waste_explore = sum(
        1 for event in events if event.get("waste_category") in {"re_read", "oversize_result"}
    )
    retries = sum(
        1 for event in events if event.get("waste_category") in {"retry_loop", "blind_retry"}
    )

    if outcome_label == "error_exit" or errors >= 3:
        primary = "tool_misuse"
    elif retries >= 2:
        primary = "loop_stall"
    elif reads > edits * 5 and edits == 0:
        primary = "over_exploration"
    elif reads > 20 and edits < 3:
        primary = "bug_mislocalization"
    elif edits >= 2 and outcome_label in {"partial", "reverted"}:
        primary = "wrong_fix"
    elif edits >= 1 and outcome_label == "partial":
        primary = "incomplete_fix"
    elif waste_explore >= 3:
        primary = "context_loss"
    elif outcome_label == "abandoned" and edits == 0:
        primary = "premature_stop"
    elif bash == 0 and outcome_label in {"partial", "abandoned"}:
        primary = "test_neglect"
    else:
        primary = "incomplete_fix"

    secondary: str | None = None
    if failure_signature and "error_waste" in failure_signature:
        secondary = "context_loss"
    elif retries:
        secondary = "loop_stall"
    return primary, secondary


__all__ = ["classify_failure"]
