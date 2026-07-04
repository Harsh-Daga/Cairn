"""Behavioral drift detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_behavioral_drift(ctx: dict[str, Any]) -> Insight | None:
    drift = ctx.get("behavioral_drift")
    if not drift or not drift.get("drift"):
        return None
    kind = str(drift.get("kind", "joint_shock"))
    top_dims = drift.get("top_dims", []) or []
    dim_text = ", ".join(f"{d['axis']}={d['delta']:+.2f}" for d in top_dims[:5]) or "n/a"
    evidence: dict[str, Any] = {
        "kind": kind,
        "project": drift.get("project"),
        "model": drift.get("model"),
        "d_squared": drift.get("d_squared"),
        "threshold": drift.get("threshold"),
        "top_dims": top_dims,
    }
    return Insight(
        id="behavioral-drift",
        severity="warning",
        title="Behavioral drift detected",
        body=(
            f"Your agent's behavior changed this week ({kind}). Top dimension deltas: {dim_text}."
        ),
        evidence=evidence,
        savings_estimate=None,
        action="cairn behavior",
        difficulty_aware=True,
    )
