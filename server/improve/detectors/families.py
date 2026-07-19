"""Family aggregators — one board card per ADR-04 family when producers fire."""

from __future__ import annotations

from typing import Any

from server.improve.detectors._types import EstimateKind, FixPayload, Insight
from server.improve.detectors.error_streak import rule_error_streak
from server.improve.detectors.failing_command import rule_failing_command
from server.improve.detectors.identical_calls import rule_identical_tool_calls
from server.improve.detectors.multi_model_spread import rule_multi_model_cost_spread
from server.improve.detectors.rebilling_waste import rule_rebilling_waste
from server.improve.detectors.reread_hotspot import rule_reread_hotspot
from server.improve.detectors.retry_loops import rule_retry_loops_detected
from server.improve.detectors.stale_tool_results import rule_stale_tool_results
from server.improve.detectors.unused_tools import rule_unused_tools

RETRY_ALIAS_IDS = (
    "retry-loops-detected",
    "error-streak",
    "failing-command",
    "identical-tool-calls",
)
CONTEXT_ALIAS_IDS = (
    "reread-hotspot",
    "rebilling-waste",
    "stale-tool-results",
)
MODEL_ALIAS_IDS = ("multi-model-cost-spread",)
SCHEMA_ALIAS_IDS = ("unused-tools",)

FAMILY_ALIAS_IDS: frozenset[str] = frozenset(
    (*RETRY_ALIAS_IDS, *CONTEXT_ALIAS_IDS, *MODEL_ALIAS_IDS, *SCHEMA_ALIAS_IDS)
)


def consolidate_family_insights(ctx: dict[str, Any]) -> list[Insight]:
    """Run producers and emit at most one insight per canonical family."""
    families: list[Insight] = []
    retry = _retry_storm(ctx)
    if retry is not None:
        families.append(retry)
    thrash = _context_thrash(ctx)
    if thrash is not None:
        families.append(thrash)
    model = _model_mismatch(ctx)
    if model is not None:
        families.append(model)
    schema = _stale_tool_schema(ctx)
    if schema is not None:
        families.append(schema)
    return families


def _collect(producers: list[Insight | None]) -> list[Insight]:
    return [item for item in producers if item is not None]


def _pick_primary(items: list[Insight]) -> Insight:
    severity_rank = {"error": 0, "warning": 1, "suggestion": 2, "info": 3}
    return min(
        items,
        key=lambda item: (
            severity_rank.get(item.severity, 4),
            -(item.savings_estimate or 0.0),
            item.id,
        ),
    )


def _merge_span_ids(items: list[Insight], ctx: dict[str, Any], key: str) -> list[str]:
    spans: list[str] = []
    for item in items:
        spans.extend(item.span_ids)
        evidence_spans = item.evidence.get("span_ids")
        if isinstance(evidence_spans, list):
            spans.extend(str(span) for span in evidence_spans)
    ctx_spans = ctx.get(key) or []
    if isinstance(ctx_spans, list):
        spans.extend(str(span) for span in ctx_spans)
    # Preserve order, drop empties.
    seen: set[str] = set()
    out: list[str] = []
    for span in spans:
        if span and span not in seen:
            seen.add(span)
            out.append(span)
        if len(out) >= 12:
            break
    return out


def _retry_storm(ctx: dict[str, Any]) -> Insight | None:
    producers = _collect(
        [
            rule_retry_loops_detected(ctx),
            rule_error_streak(ctx),
            rule_failing_command(ctx),
            rule_identical_tool_calls(ctx),
        ]
    )
    attempts = int(ctx.get("retry_storm_attempts", 0) or 0)
    events = (
        int(ctx.get("retry_loop_events", 0) or 0)
        + int(ctx.get("identical_call_events", 0) or 0)
        + int(ctx.get("max_error_streak", 0) or 0)
    )
    if not producers and attempts < 3 and events < 3:
        return None
    if not producers and attempts < 3:
        return None
    primary = _pick_primary(producers) if producers else None
    storm_cost = ctx.get("retry_storm_cost_usd")
    savings = None
    unavailable = None
    estimate_kind: EstimateKind = "unavailable"
    if isinstance(storm_cost, (int, float)) and float(storm_cost) > 0:
        days = max(1, int(ctx.get("days", 14)))
        savings = round(float(storm_cost) * (7.0 / days) * 0.5, 2)
        estimate_kind = "conservative"
    elif primary is not None and primary.savings_estimate is not None:
        savings = primary.savings_estimate
        estimate_kind = primary.estimate_kind or "conservative"
    else:
        unavailable = (
            primary.savings_unavailable_reason
            if primary is not None and primary.savings_unavailable_reason
            else "Retry counts are available, but storm cost could not be attributed."
        )
    alias_ids = [item.id for item in producers]
    span_ids = _merge_span_ids(producers, ctx, "retry_storm_span_ids")
    attempt_n = max(attempts, events, 3 if producers else 0)
    body_bits = [item.title for item in producers] or ["Repeated failed or identical tool attempts"]
    return Insight(
        id="retry-storm",
        severity=primary.severity if primary is not None else "warning",
        title="Retry storm",
        body=(
            f"Merged retry-family signals ({', '.join(body_bits)}). "
            f"Observed at least {attempt_n} failed or repeated attempts in the window."
        ),
        evidence={
            "alias_ids": alias_ids,
            "attempts": attempt_n,
            "storm_cost_usd": storm_cost,
            "producers": [item.evidence for item in producers],
            "span_ids": span_ids,
        },
        savings_estimate=savings,
        savings_unavailable_reason=unavailable,
        fix=(
            primary.fix
            if primary is not None and primary.fix is not None
            else FixPayload(
                kind="instruction",
                label="Copy retry-breaker rule",
                value=(
                    "After a tool fails or returns the same result, quote the error or prior "
                    "output and change the command, input, or strategy before retrying."
                ),
            )
        ),
        action="cairn optimize",
        family="retry_storm",
        estimate_kind=estimate_kind,
        confidence=min(0.9, 0.45 + 0.1 * len(producers) + (0.1 if attempt_n >= 5 else 0.0)),
        coverage="Alias detectors remain evidence producers; this card owns board lifecycle.",
        subject_key="family:retry_storm",
        span_ids=span_ids,
        alias_ids=alias_ids,
    )


def _context_thrash(ctx: dict[str, Any]) -> Insight | None:
    producers = _collect(
        [
            rule_reread_hotspot(ctx),
            rule_rebilling_waste(ctx),
            rule_stale_tool_results(ctx),
        ]
    )
    if not producers:
        return None
    primary = _pick_primary(producers)
    file_costs = ctx.get("context_thrash_file_costs") or []
    span_ids = _merge_span_ids(producers, ctx, "context_thrash_span_ids")
    savings = primary.savings_estimate
    unavailable = primary.savings_unavailable_reason if savings is None else None
    return Insight(
        id="context-thrash",
        severity=primary.severity,
        title="Context thrash",
        body=(
            "Merged context-family signals ("
            + ", ".join(item.title for item in producers)
            + "). Repeated retrieval or re-billing is inflating context cost."
        ),
        evidence={
            "alias_ids": [item.id for item in producers],
            "file_costs": file_costs[:8],
            "producers": [item.evidence for item in producers],
            "span_ids": span_ids,
        },
        savings_estimate=savings,
        savings_unavailable_reason=unavailable,
        fix=primary.fix
        or FixPayload(
            kind="instruction",
            label="Copy context thrash rule",
            value=(
                "Reuse earlier file or tool results when content hashes are unchanged; "
                "summarize stale tool output instead of re-billing it each turn."
            ),
        ),
        action=primary.action or "cairn optimize",
        family="context_thrash",
        estimate_kind=primary.estimate_kind
        or ("unavailable" if savings is None else "conservative"),
        confidence=min(0.9, 0.5 + 0.15 * len(producers)),
        coverage="Per-file costs are descriptive when present; avoidability is not proven.",
        subject_key="family:context_thrash",
        span_ids=span_ids,
        alias_ids=[item.id for item in producers],
    )


def _model_mismatch(ctx: dict[str, Any]) -> Insight | None:
    producer = rule_multi_model_cost_spread(ctx)
    if producer is None:
        return None
    samples = int(ctx.get("model_comparable_samples", 0) or 0)
    diagnostic = samples < 8
    fix = producer.fix
    if diagnostic:
        fix = FixPayload(
            kind="manual",
            label="Compare matched samples before routing",
            value=(
                "Do not switch models for cost alone. Collect at least eight sessions with "
                "comparable difficulty/outcome bands before changing default routing."
            ),
        )
    return Insight(
        id="model-mismatch",
        severity="info",
        title="Model mismatch watch",
        body=producer.body
        + (
            " Comparable matched samples are insufficient for a cheaper-model recommendation."
            if diagnostic
            else " Comparable samples support a conservative routing review."
        ),
        evidence={
            **dict(producer.evidence),
            "alias_ids": ["multi-model-cost-spread"],
            "comparable_samples": samples,
        },
        savings_estimate=None,
        savings_unavailable_reason=(
            "Model cost differences are not savings until tasks are matched for quality and "
            "difficulty with adequate samples."
        ),
        fix=fix,
        diagnostic=True,
        action=None,
        family="model_mismatch",
        estimate_kind="unavailable",
        confidence=0.35 if diagnostic else 0.55,
        coverage=f"comparable_samples={samples}; cheaper-model advice gated at n≥8",
        subject_key="family:model_mismatch",
        alias_ids=["multi-model-cost-spread"],
    )


def _stale_tool_schema(ctx: dict[str, Any]) -> Insight | None:
    producer = rule_unused_tools(ctx)
    if producer is None:
        return None
    coverage = (
        ctx.get("unused_tools_coverage")
        or producer.coverage
        or ("Schema-token attribution is partial when tool names cannot be linked to schema rows.")
    )
    return Insight(
        id="stale-tool-schema",
        severity=producer.severity,
        title="Stale tool schema",
        body=producer.body,
        evidence={
            **dict(producer.evidence),
            "alias_ids": ["unused-tools"],
            "schema_tokens": ctx.get("tool_schema_tokens"),
        },
        savings_estimate=producer.savings_estimate,
        savings_unavailable_reason=producer.savings_unavailable_reason,
        fix=producer.fix,
        action=producer.action,
        difficulty_aware=True,
        family="stale_tool_schema",
        estimate_kind=producer.estimate_kind or "unavailable",
        confidence=0.5,
        coverage=str(coverage),
        subject_key="family:stale_tool_schema",
        alias_ids=["unused-tools"],
    )
