"""Multi-model cost spread detector."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import FixPayload, Insight

MIN_COMPARABLE_SAMPLES = 8


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
    samples = int(ctx.get("model_comparable_samples", 0) or 0)
    can_recommend = samples >= MIN_COMPARABLE_SAMPLES
    if can_recommend:
        fix = FixPayload(
            kind="settings",
            label="Review matched routing",
            value=(
                f"With {samples} comparable sessions, consider routing routine work to "
                f"{cheap_name} and reserving {expensive_name} where quality advantage is measured."
            ),
        )
    else:
        fix = FixPayload(
            kind="manual",
            label="Collect matched samples before routing changes",
            value=(
                f"Using {len(models)} models ({names}). Do not default to {cheap_name} for cost "
                f"alone — gather at least {MIN_COMPARABLE_SAMPLES} sessions with comparable "
                "difficulty/outcome bands first."
            ),
        )
    return Insight(
        id="multi-model-cost-spread",
        severity="info",
        title="Multiple models in use",
        body=(
            f"Using {len(models)} models: {names}. "
            f"{expensive_name} sessions cost {ratio:.1f}x more than {cheap_name} "
            "on aggregate spend."
        ),
        evidence={
            "models": models,
            "ratio": ratio,
            "comparable_samples": samples,
            "recommendation_gated": not can_recommend,
        },
        savings_estimate=None,
        savings_unavailable_reason=(
            "Model cost differences are not savings until tasks are matched for quality and "
            "difficulty."
        ),
        fix=fix,
        diagnostic=True,
        action=None,
        estimate_kind="unavailable",
        confidence=0.55 if can_recommend else 0.35,
        coverage=f"comparable_samples={samples}; gate={MIN_COMPARABLE_SAMPLES}",
        subject_key="detector:multi-model-cost-spread",
    )
