"""Cost outliers for a difficulty bucket."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_cost_anomaly(ctx: dict[str, Any]) -> Insight | None:
    anomalies = ctx.get("cost_anomalies") or []
    if not isinstance(anomalies, list) or not anomalies:
        return None
    top = anomalies[0]
    trace_id = str(top.get("trace_id", ""))
    cost = float(top.get("cost", 0.0))
    threshold = float(top.get("threshold", 0.0))
    return Insight(
        id="cost-anomaly",
        severity="warning",
        title="Session cost anomaly",
        body=(
            f"Trace {trace_id[:12]}… cost ${cost:.2f} exceeds the bucket threshold "
            f"${threshold:.2f} (μ+3σ, min 20 baseline traces)."
        ),
        evidence={"trace_id": trace_id, "cost": cost, "threshold": threshold},
        savings_estimate=None,
        action="cairn check --max-tail-cost",
    )
