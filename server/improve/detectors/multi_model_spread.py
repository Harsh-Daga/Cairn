"""Multi-model cost spread detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import Insight


def rule_multi_model_cost_spread(ctx: dict[str, Any]) -> Insight | None:
    models = ctx.get("model_costs_30d", {})
    if len(models) <= 2:
        return None
    if not all(v > 0 for v in models.values()):
        return None
    sorted_models = sorted(models.items(), key=lambda kv: kv[1])
    cheap_name, cheap_cost = sorted_models[0]
    expensive_name, expensive_cost = sorted_models[-1]
    if cheap_cost <= 0:
        return None
    ratio = expensive_cost / cheap_cost
    names = ", ".join(m for m, _ in sorted(models.items(), key=lambda kv: -kv[1]))
    return Insight(
        id="multi-model-cost-spread",
        severity="info",
        title="Multiple models in use",
        body=(
            f"Using {len(models)} models: {names}. "
            f"{expensive_name} sessions cost {ratio:.1f}x more than {cheap_name} for similar work."
        ),
        evidence={"models": models, "ratio": ratio},
        savings_estimate=None,
        action=None,
    )
