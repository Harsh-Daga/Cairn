"""Tool retry loop detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import FixPayload, Insight, LiveDetection


def detect_live_retry_loops(spans: list[dict[str, Any]]) -> LiveDetection | None:
    """Detect tool-call → error → same-tool retries within three later spans."""
    hits: list[tuple[int, str]] = []
    for index, span in enumerate(spans):
        if span.get("kind") != "tool_call" or not span.get("name"):
            continue
        name = str(span["name"])
        window = spans[index + 1 : index + 5]
        saw_error = False
        for later in window:
            if later.get("status") == "error":
                saw_error = True
            if saw_error and later.get("kind") == "tool_call" and later.get("name") == name:
                hits.append((int(span.get("seq") or 0), name))
                break
    if len(hits) < 2:
        return None
    first_seq, name = hits[0]
    return LiveDetection(
        pattern="retry_loops",
        count=len(hits) + 1,
        first_seen_seq=first_seq,
        advice=(
            f"You've retried {name} {len(hits) + 1}× after errors — read the error output and "
            "change the input or strategy before retrying."
        ),
        priority=40,
    )


def rule_retry_loops_detected(ctx: dict[str, Any]) -> Insight | None:
    count = int(ctx.get("retry_loop_events", 0))
    if count <= 5:
        return None
    return Insight(
        id="retry-loops-detected",
        severity="warning",
        title="Tool retry loops",
        body=(
            f"{count} tool retry loops detected. "
            "Agent is hitting errors and retrying the same tool call."
        ),
        evidence={"events": count},
        savings_estimate=None,
        savings_unavailable_reason=(
            "Retry counts are available, but per-retry cost is not reliably attributed."
        ),
        fix=FixPayload(
            kind="instruction",
            label="Copy retry-breaker rule",
            value=(
                "After a tool fails, quote the relevant error and change the command, input, or "
                "strategy before retrying."
            ),
        ),
        action="cairn optimize",
    )
