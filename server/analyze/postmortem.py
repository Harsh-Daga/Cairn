"""Deterministic diagnose-based session postmortems (no remote LLM)."""

from __future__ import annotations

from typing import Any

from server.models.outcome import Diagnostic, Outcome
from server.models.span import Span
from server.models.trace import Trace

UNCERTAINTY_DEFAULT = (
    "This postmortem is recorded localization from the diagnose cascade. "
    "It does not establish that a model, prompt, rule, or tool caused the outcome."
)


def build_postmortem(
    *,
    trace: Trace,
    spans: list[Span],
    diagnostic: Diagnostic | None,
    outcome: Outcome | None,
) -> dict[str, Any] | None:
    """Build a structured postmortem when failure or low quality is recorded."""
    if not _eligible(outcome, diagnostic, spans):
        return None

    ordered = sorted(spans, key=lambda span: span.seq)
    by_id = {span.span_id: span for span in ordered}
    origin = None
    if diagnostic and diagnostic.failure_origin_span_id:
        origin = by_id.get(diagnostic.failure_origin_span_id)
    if origin is None:
        origin = next((span for span in ordered if span.status == "error"), None)
    if origin is None and diagnostic and diagnostic.cascade_root_span_id:
        origin = by_id.get(diagnostic.cascade_root_span_id)

    origin_seq = origin.seq if origin is not None else None
    prior_context = [
        _span_summary(span) for span in ordered if origin_seq is not None and span.seq < origin_seq
    ][-5:]
    action = _span_summary(origin) if origin is not None else None

    downstream = [span for span in ordered if origin_seq is not None and span.seq > origin_seq]
    retry_spans = [
        span
        for span in downstream
        if span.waste_category in {"retry_loop", "blind_retry", "identical_call"}
        or span.status == "error"
    ]
    waste_tokens = sum(int(span.waste_tokens or 0) for span in downstream)
    retry_tokens = sum(int(span.waste_tokens or 0) for span in retry_spans)
    cascade_tokens = diagnostic.cascade_blast_tokens if diagnostic is not None else None
    total_tokens = int(trace.input_tokens or 0) + int(trace.output_tokens or 0)
    session_cost = float(trace.cost or 0.0)
    attributed_cost = None
    if session_cost > 0 and total_tokens > 0 and waste_tokens > 0:
        attributed_cost = round(session_cost * (waste_tokens / total_tokens), 4)

    uncertainty = [UNCERTAINTY_DEFAULT]
    if diagnostic is None:
        uncertainty.append("No persisted diagnose row; using error spans only.")
    if origin is None:
        uncertainty.append("No failure origin span could be localized.")
    if attributed_cost is None:
        uncertainty.append(
            "Downstream dollar impact unavailable without attributable cost and waste tokens."
        )

    prior_tail = prior_context[-1] if prior_context else None
    steps: list[dict[str, Any]] = [
        {
            "kind": "degradation_began",
            "label": "Step where degradation began",
            "span_id": origin.span_id if origin is not None else None,
            "seq": origin_seq,
            "summary": (
                f"Localized at seq {origin_seq} ({origin.kind}/{origin.name or 'span'})."
                if origin is not None
                else "Degradation origin unavailable."
            ),
        },
        {
            "kind": "context_had",
            "label": "Evidence/context the agent had",
            "span_id": prior_tail["span_id"] if prior_tail is not None else None,
            "seq": prior_tail["seq"] if prior_tail is not None else None,
            "summary": (
                f"{len(prior_context)} prior span(s) immediately before the origin."
                if prior_context
                else "No prior spans were available before the origin."
            ),
            "items": prior_context,
        },
        {
            "kind": "action_taken",
            "label": "Action taken at origin",
            "span_id": action["span_id"] if action is not None else None,
            "seq": action["seq"] if action is not None else None,
            "summary": (
                str(action["label"]) if action is not None else "No origin action recorded."
            ),
        },
        {
            "kind": "downstream",
            "label": "Downstream retries / waste / cost",
            "span_id": retry_spans[0].span_id if retry_spans else None,
            "seq": retry_spans[0].seq if retry_spans else None,
            "summary": (
                f"{len(retry_spans)} retry/error span(s) after origin; "
                f"{waste_tokens} downstream waste tokens"
                + (f"; cascade blast {cascade_tokens} tokens" if cascade_tokens is not None else "")
                + (f"; attributed ~${attributed_cost:.4f}" if attributed_cost is not None else "")
                + "."
            ),
            "retry_span_ids": [span.span_id for span in retry_spans[:12]],
            "waste_tokens": waste_tokens,
            "retry_waste_tokens": retry_tokens,
            "cascade_blast_tokens": cascade_tokens,
            "attributed_cost_usd": attributed_cost,
        },
    ]

    span_links: list[dict[str, str]] = []
    for span_id in [
        origin.span_id if origin is not None else None,
        diagnostic.cascade_root_span_id if diagnostic is not None else None,
        *[span.span_id for span in retry_spans[:5]],
    ]:
        if span_id and span_id not in {link["span_id"] for link in span_links}:
            span_links.append(
                {
                    "span_id": span_id,
                    "href": f"/sessions/{trace.trace_id}?span={span_id}&tab=postmortem",
                    "label": f"Open span {span_id[:12]}",
                }
            )

    markdown = _render_markdown(
        trace_id=trace.trace_id,
        diagnostic=diagnostic,
        outcome=outcome,
        steps=steps,
        uncertainty=uncertainty,
        span_links=span_links,
    )
    return {
        "trace_id": trace.trace_id,
        "eligible": True,
        "source": "diagnose_cascade",
        "reflector": None,
        "primary_category": diagnostic.primary_category if diagnostic else None,
        "secondary_category": diagnostic.secondary_category if diagnostic else None,
        "failure_signature": diagnostic.failure_signature if diagnostic else None,
        "outcome_label": outcome.outcome_label if outcome else None,
        "quality_score": outcome.quality_score if outcome else None,
        "steps": steps,
        "uncertainty": uncertainty,
        "span_links": span_links,
        "markdown": markdown,
        "limitation": UNCERTAINTY_DEFAULT,
    }


def _eligible(
    outcome: Outcome | None,
    diagnostic: Diagnostic | None,
    spans: list[Span],
) -> bool:
    if diagnostic is not None:
        return True
    if outcome is not None:
        label = (outcome.outcome_label or "").lower()
        if label in {"failed", "failure", "error", "regressed"}:
            return True
        if outcome.tests_failed is not None and outcome.tests_failed > 0:
            return True
        if outcome.quality_score is not None and outcome.quality_score < 50:
            return True
        if outcome.human_label == "down":
            return True
    return any(span.status == "error" for span in spans)


def _span_summary(span: Span | None) -> dict[str, Any] | None:
    if span is None:
        return None
    name = span.name or span.kind
    waste = f", waste={span.waste_category}" if span.waste_category else ""
    status = f", status={span.status}" if span.status else ""
    return {
        "span_id": span.span_id,
        "seq": span.seq,
        "kind": span.kind,
        "name": span.name,
        "status": span.status,
        "waste_category": span.waste_category,
        "label": f"seq {span.seq}: {span.kind}/{name}{status}{waste}",
    }


def _render_markdown(
    *,
    trace_id: str,
    diagnostic: Diagnostic | None,
    outcome: Outcome | None,
    steps: list[dict[str, Any]],
    uncertainty: list[str],
    span_links: list[dict[str, str]],
) -> str:
    lines = [
        f"# Cairn postmortem · `{trace_id}`",
        "",
        "Source: deterministic diagnose cascade (not a causal narrative).",
        "",
    ]
    if diagnostic is not None:
        lines.extend(
            [
                "## Diagnose summary",
                f"- Primary: {diagnostic.primary_category or 'unavailable'}",
                f"- Secondary: {diagnostic.secondary_category or 'unavailable'}",
                f"- Signature: {diagnostic.failure_signature or 'unavailable'}",
                f"- Cascade blast tokens: {diagnostic.cascade_blast_tokens}",
                "",
            ]
        )
    if outcome is not None:
        lines.extend(
            [
                "## Outcome",
                f"- Label: {outcome.outcome_label or 'unavailable'}",
                f"- Quality: {outcome.quality_score}",
                "",
            ]
        )
    lines.append("## Steps")
    for step in steps:
        lines.append(f"### {step['label']}")
        lines.append(str(step.get("summary") or ""))
        items = step.get("items") or []
        for item in items:
            lines.append(f"- {item['label']}")
        lines.append("")
    lines.append("## Span links")
    for link in span_links:
        lines.append(f"- [{link['label']}]({link['href']})")
    if not span_links:
        lines.append("- None")
    lines.extend(["", "## Uncertainty"])
    for note in uncertainty:
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## Optional reflector",
            "Not included. Any LLM enhancement must be explicitly opt-in and labeled separately.",
        ]
    )
    return "\n".join(lines) + "\n"
