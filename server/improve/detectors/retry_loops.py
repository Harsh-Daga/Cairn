"""Tool retry loop detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


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
        action="cairn optimize",
    )
