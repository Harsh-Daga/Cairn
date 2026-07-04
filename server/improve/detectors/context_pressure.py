"""Context window pressure detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import (
    Insight,
    context_rot_warning_pct,
    context_rot_waste_pct,
)


def rule_context_window_pressure(ctx: dict[str, Any]) -> Insight | None:
    sessions = ctx.get("high_context_sessions", [])
    if not sessions:
        return None
    top = max(sessions, key=lambda s: s["peak_context_pct"])
    pct = top["peak_context_pct"]
    warn_pct = context_rot_warning_pct()
    severity = "error" if pct > context_rot_waste_pct() else "warning"
    if pct < warn_pct:
        return None
    sid = top["run_id"][:12]
    return Insight(
        id="context-window-pressure",
        severity=severity,
        title="Context window pressure",
        body=(
            f"Session {sid} peaked at {pct:.0f}% of context window — "
            "context rot is setting in; compaction, clearing consumed tool "
            "results, or task splitting would reduce cost."
        ),
        evidence={"run_id": top["run_id"], "peak_context_pct": pct},
        savings_estimate=None,
        action="cairn show last",
    )
