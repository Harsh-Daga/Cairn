"""Trace list, detail, diff, and replay payload builders."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from server.analyze.corrections import build_corrections_for_trace
from server.analyze.diff import (
    MAX_DIFF_SPANS_PER_SIDE,
    MAX_LCS_CELLS,
    build_trace_diff_payload,
)
from server.analyze.handoff import build_handoff_for_trace
from server.analyze.postmortem import build_postmortem
from server.analyze.verification import (
    build_receipt_dict,
    build_receipt_for_trace,
    render_receipt_markdown,
    verification_status_from_fields,
)
from server.api.schemas import (
    CorrectionsResponse,
    HandoffResponse,
    McpConsultation,
    PostmortemResponse,
    QueryFilterError,
    QueryFilterToken,
    ReceiptResponse,
    ReplayCheckpoint,
    ReplayResponse,
    ReplaySummary,
    SessionShield,
    SpanLink,
    SpanNode,
    TraceDetailResponse,
    TraceDiffAnalysis,
    TraceDiffChange,
    TraceDiffComparability,
    TraceDiffEvidence,
    TraceDiffRegion,
    TraceDiffResponse,
    TraceRow,
    TracesListResponse,
)
from server.configuration import load_config
from server.models.context_region import ContextRegion
from server.models.data_quality import DataQuality
from server.models.outcome import Diagnostic, Outcome
from server.models.span import Span
from server.models.time_range import ResolvedTimeRange
from server.query_filters import parse_filter
from server.store.repos.corrections import CorrectionRepo
from server.store.repos.data_quality import DataQualityRepo
from server.store.repos.diagnostics import DiagnosticRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.receipts import ReceiptRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceListFilters, TraceRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.resources import build_resource_report, resource_shield_fields

MAX_REPLAY_CHECKPOINTS = 40
MAX_REPLAY_SERIALIZED_SPANS = 5_000


def _duration_ms(started_at: str | None, ended_at: str | None) -> int | None:
    if not started_at or not ended_at:
        return None
    try:
        duration = datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)
    except ValueError:
        return None
    return max(0, int(duration.total_seconds() * 1000))


def _verification_state(
    outcome: sqlite3.Row | None,
) -> Literal["verified", "failed", "debt", "unverified", "unknown"]:
    if outcome is None:
        return verification_status_from_fields(
            tests_failed=None,
            build_status=None,
            tests_run=None,
            outcome_label=None,
            has_outcome=False,
        )
    return verification_status_from_fields(
        tests_failed=int(outcome["tests_failed"]) if outcome["tests_failed"] is not None else None,
        build_status=str(outcome["build_status"]) if outcome["build_status"] is not None else None,
        tests_run=int(outcome["tests_run"]) if outcome["tests_run"] is not None else None,
        outcome_label=(
            str(outcome["outcome_label"]) if outcome["outcome_label"] is not None else None
        ),
        has_outcome=True,
    )


def _trace_row(
    trace: Any,
    *,
    outcome: sqlite3.Row | None = None,
    quality: sqlite3.Row | None = None,
    token_flow: list[int] | None = None,
    first_user_request: str | None = None,
    top_files: list[str] | None = None,
) -> TraceRow:
    data_quality_state: Literal["measured", "partial", "degraded", "unavailable"] = "unavailable"
    if quality is not None:
        if int(quality["dropped_events"] or 0) > 0:
            data_quality_state = "degraded"
        elif float(quality["pct_tokens_estimated"] or 0) > 0:
            data_quality_state = "partial"
        else:
            data_quality_state = "measured"
    return TraceRow(
        trace_id=trace.trace_id,
        source=trace.source,
        title=trace.title,
        project=trace.project,
        actor_id=trace.actor_id,
        model=trace.model,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        status=trace.status,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        cost=trace.cost,
        cost_source=trace.cost_source,
        span_count=trace.span_count,
        waste_tokens=trace.waste_tokens,
        difficulty=trace.difficulty,
        duration_ms=_duration_ms(trace.started_at, trace.ended_at),
        token_flow=token_flow or [],
        quality_score=(
            float(outcome["quality_score"])
            if outcome is not None and outcome["quality_score"] is not None
            else None
        ),
        outcome_label=(
            str(outcome["outcome_label"])
            if outcome is not None and outcome["outcome_label"] is not None
            else None
        ),
        verification_state=_verification_state(outcome),
        first_user_request=first_user_request,
        top_files=top_files or [],
        data_quality_state=data_quality_state,
    )


def _trace_list_rows(conn: sqlite3.Connection, traces: list[Any]) -> list[TraceRow]:
    if not traces:
        return []
    trace_ids = [str(trace.trace_id) for trace in traces]
    placeholders = ",".join("?" for _ in trace_ids)
    outcomes = {
        str(row["trace_id"]): row
        for row in conn.execute(
            f"""
            SELECT trace_id, tests_run, tests_failed, build_status, quality_score, outcome_label
            FROM outcomes WHERE trace_id IN ({placeholders})
            """,
            trace_ids,
        ).fetchall()
    }
    qualities = {
        str(row["trace_id"]): row
        for row in conn.execute(
            f"""
            SELECT trace_id, pct_tokens_estimated, dropped_events
            FROM data_quality WHERE trace_id IN ({placeholders})
            """,
            trace_ids,
        ).fetchall()
    }
    flow: dict[str, list[int]] = defaultdict(list)
    first_request: dict[str, str] = {}
    files: dict[str, Counter[str]] = defaultdict(Counter)
    for row in conn.execute(
        f"""
        SELECT trace_id, kind, text_inline, path_rel, input_tokens, output_tokens
        FROM spans
        WHERE trace_id IN ({placeholders})
        ORDER BY trace_id, seq
        """,
        trace_ids,
    ).fetchall():
        trace_id = str(row["trace_id"])
        if row["kind"] == "llm_call" and len(flow[trace_id]) < 20:
            flow[trace_id].append(int(row["input_tokens"] or 0) + int(row["output_tokens"] or 0))
        if row["kind"] == "user_msg" and trace_id not in first_request and row["text_inline"]:
            first_request[trace_id] = str(row["text_inline"])[:160]
        if row["path_rel"]:
            files[trace_id][str(row["path_rel"])] += 1
    return [
        _trace_row(
            trace,
            outcome=outcomes.get(str(trace.trace_id)),
            quality=qualities.get(str(trace.trace_id)),
            token_flow=flow.get(str(trace.trace_id), []),
            first_user_request=first_request.get(str(trace.trace_id)),
            top_files=[
                path for path, _count in files.get(str(trace.trace_id), Counter()).most_common(3)
            ],
        )
        for trace in traces
    ]


def build_traces_list(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int | None = None,
    start: str | None = None,
    end: str | None = None,
    time_range: ResolvedTimeRange | None = None,
    source: str | None = None,
    project: str | None = None,
    actor: str | None = None,
    agent: str | None = None,
    q: str | None = None,
    sort: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> TracesListResponse:
    parsed_filter = parse_filter(q or "")
    filters = TraceListFilters(
        workspace_id=workspace_id,
        days=days,
        start=start,
        end=end,
        source=source,
        project=project,
        actor=actor,
        agent=agent,
        q=q,
        parsed_filter=parsed_filter,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    traces = TraceRepo.list(conn, filters)
    total = TraceRepo.count(conn, filters)
    return TracesListResponse(
        traces=_trace_list_rows(conn, traces),
        total=total,
        limit=limit,
        offset=offset,
        resolved_range=time_range,
        filter_phrase=parsed_filter.phrase,
        filter_tokens=[
            QueryFilterToken(
                raw=token.raw,
                field=token.field,
                value=token.value,
                comparison=token.comparison,
                available=token.available,
            )
            for token in parsed_filter.tokens
        ],
        filter_errors=[
            QueryFilterError(token=error.token, message=error.message)
            for error in parsed_filter.errors
        ],
    )


def _build_span_tree(spans: list[Span]) -> list[SpanNode]:
    by_id = {span.span_id: SpanNode(span=span) for span in spans}
    roots: list[SpanNode] = []
    for node in by_id.values():
        parent_id = node.span.parent_span_id
        if parent_id and parent_id in by_id:
            by_id[parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


def _session_shields(
    conn: sqlite3.Connection,
    *,
    trace: Any,
    spans: list[Span],
    outcome: Outcome | None,
    quality: DataQuality | None,
    workspace_root: Path | None = None,
) -> list[SessionShield]:
    tests_failed = outcome.tests_failed if outcome else None
    build_failed = (
        (outcome.build_status or "").lower() in {"fail", "failed", "error"} if outcome else False
    )
    verification_attention = bool((tests_failed or 0) > 0 or build_failed)
    paths = sorted({span.path_rel for span in spans if span.path_rel})
    inline_text = sum(1 for span in spans if span.text_inline)
    trace_id = str(trace.trace_id)
    tests_run = outcome.tests_run if outcome and outcome.tests_run is not None else "unknown"
    tests_failed_label = tests_failed if tests_failed is not None else "unknown"
    build_status = outcome.build_status if outcome and outcome.build_status else "unknown"
    path_label = "path" if len(paths) == 1 else "paths"
    payload_label = "payload" if inline_text == 1 else "payloads"
    if workspace_root is not None:
        report = build_resource_report(
            conn,
            workspace_root=workspace_root,
            workspace_id=str(trace.workspace_id),
        )
        fields = resource_shield_fields(report)
        resource_shield = SessionShield(
            shield="resource",
            state=fields["state"],
            summary=fields["summary"],
            facts=[
                *fields["facts"],
                f"Span count: {len(spans)}.",
                (
                    f"Dropped ingest events: {quality.dropped_events}."
                    if quality is not None
                    else "Ingest data-quality record unavailable."
                ),
            ],
            limitation=(
                f"{fields['limitation']} Session-level process/queue samples were not captured; "
                "figures above are workspace inventory."
            ),
            action_label="Review settings",
            action_path="/settings",
        )
    else:
        resource_shield = SessionShield(
            shield="resource",
            state="unavailable",
            summary="Session process, queue, memory, and disk budgets were not captured.",
            facts=[
                f"Span count: {len(spans)}.",
                (
                    f"Dropped ingest events: {quality.dropped_events}."
                    if quality is not None
                    else "Ingest data-quality record unavailable."
                ),
            ],
            limitation=(
                "No healthy resource claim is made without measured process and storage data."
            ),
            action_label="Review settings",
            action_path="/settings",
        )
    return [
        SessionShield(
            shield="verification",
            state="attention" if verification_attention else "unknown",
            summary=(
                "Recorded verification has a failure."
                if verification_attention
                else "Recorded outcome evidence is incomplete."
            ),
            facts=[
                f"Tests run: {tests_run}.",
                f"Tests failed: {tests_failed_label}.",
                f"Build status: {build_status}.",
            ],
            limitation=(
                "Receipt v1 cannot prove validation after the final edit; "
                "claim-to-evidence extraction remains unavailable."
            ),
            action_label="Review receipt",
            action_path=f"/sessions/{trace_id}?tab=receipt",
        ),
        SessionShield(
            shield="scope",
            state="unknown" if paths else "unavailable",
            summary=(
                f"Observed activity references {len(paths)} relative {path_label}."
                if paths
                else "No relative file paths were captured for scope review."
            ),
            facts=[
                f"Captured relative paths: {len(paths)}.",
                f"Observed spans: {len(spans)}.",
            ],
            limitation=(
                "No requested/allowed path policy or destructive-action enforcement is available."
            ),
            action_label="Inspect waterfall",
            action_path=f"/sessions/{trace_id}?tab=investigate",
        ),
        SessionShield(
            shield="privacy",
            state="unknown",
            summary=f"{inline_text} span {payload_label} retain inline text.",
            facts=[
                f"Cost source: {trace.cost_source}.",
                "Cairn remains loopback-only and zero-telemetry by default.",
            ],
            limitation=(
                "This session summary does not prove that the observed agent made no network calls."
            ),
            action_label="Review transcript",
            action_path=f"/sessions/{trace_id}?tab=transcript",
        ),
        resource_shield,
    ]


def build_trace_detail(
    conn: sqlite3.Connection,
    trace_id: str,
    *,
    workspace_root: Path | None = None,
) -> TraceDetailResponse | None:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    spans = SpanRepo.list_by_trace(conn, trace_id)
    link_rows = conn.execute(
        """
        SELECT from_span_id, to_span_id, link_type
        FROM span_links
        WHERE from_span_id IN (SELECT span_id FROM spans WHERE trace_id = ?)
           OR to_span_id IN (SELECT span_id FROM spans WHERE trace_id = ?)
        """,
        (trace_id, trace_id),
    ).fetchall()
    links = [
        SpanLink(
            from_span_id=str(row["from_span_id"]),
            to_span_id=str(row["to_span_id"]),
            link_type=str(row["link_type"]),
        )
        for row in link_rows
    ]
    region_rows = conn.execute(
        """
        SELECT span_id, region, tokens, cost, content_hash
        FROM context_regions
        WHERE span_id IN (SELECT span_id FROM spans WHERE trace_id = ?)
        """,
        (trace_id,),
    ).fetchall()
    regions = [ContextRegion.model_validate(dict(row)) for row in region_rows]
    consultation_rows = conn.execute(
        """SELECT event_id, trace_id, after_seq, tool_name, called_at
           FROM mcp_consultations
           WHERE trace_id = ?
           ORDER BY after_seq, called_at""",
        (trace_id,),
    ).fetchall()
    consultations = [McpConsultation.model_validate(dict(row)) for row in consultation_rows]
    quality = DataQualityRepo.get(conn, trace_id)
    outcome = OutcomeRepo.get(conn, trace_id)
    diagnostics = DiagnosticRepo.get(conn, trace_id)
    postmortem_raw = build_postmortem(
        trace=trace,
        spans=spans,
        diagnostic=diagnostics,
        outcome=outcome,
    )
    postmortem = (
        PostmortemResponse.model_validate(postmortem_raw) if postmortem_raw is not None else None
    )
    policy = None
    workspace = WorkspaceRepo.get(conn, trace.workspace_id)
    if workspace is not None and workspace.root_path:
        policy = load_config(Path(workspace.root_path)).policy
    receipt_raw = build_receipt_dict(trace=trace, spans=spans, outcome=outcome, policy=policy)
    receipt = ReceiptResponse.model_validate(
        {
            **receipt_raw,
            "markdown": render_receipt_markdown(receipt_raw),
            "persisted": False,
        }
    )
    corrections_raw = build_corrections_for_trace(conn, trace_id)
    corrections = (
        CorrectionsResponse.model_validate({**corrections_raw, "persisted": False})
        if corrections_raw is not None
        else None
    )
    return TraceDetailResponse(
        trace=trace,
        spans=spans,
        tree=_build_span_tree(spans),
        links=links,
        mcp_consultations=consultations,
        regions=regions,
        diagnostics=diagnostics,
        quality=quality,
        outcome=outcome,
        shields=_session_shields(
            conn,
            trace=trace,
            spans=spans,
            outcome=outcome,
            quality=quality,
            workspace_root=workspace_root,
        ),
        postmortem=postmortem,
        receipt=receipt,
        corrections=corrections,
        handoff=None,
    )


def build_trace_receipt(conn: sqlite3.Connection, trace_id: str) -> ReceiptResponse | None:
    """Build (and optionally reflect persisted) verification receipt for one trace."""
    receipt_raw = build_receipt_for_trace(conn, trace_id)
    if receipt_raw is None:
        return None
    stored_hash = ReceiptRepo.get_hash(conn, trace_id)
    persisted = stored_hash == receipt_raw["content_hash"]
    return ReceiptResponse.model_validate(
        {
            **receipt_raw,
            "markdown": render_receipt_markdown(receipt_raw),
            "persisted": persisted,
        }
    )


def build_trace_corrections(conn: sqlite3.Connection, trace_id: str) -> CorrectionsResponse | None:
    """Build corrections ledger, reflecting persistence when content hash matches."""
    payload = build_corrections_for_trace(conn, trace_id)
    if payload is None:
        return None
    stored_hash = CorrectionRepo.get_hash(conn, trace_id)
    persisted = stored_hash == payload["content_hash"]
    return CorrectionsResponse.model_validate({**payload, "persisted": persisted})


def build_trace_handoff(
    conn: sqlite3.Connection,
    trace_id: str,
    *,
    workspace_root: Path | str,
    char_budget: int = 3500,
) -> HandoffResponse | None:
    """Build an offline scrubbed handoff capsule."""
    root = workspace_root if isinstance(workspace_root, Path) else Path(workspace_root)
    payload = build_handoff_for_trace(conn, trace_id, workspace_root=root, char_budget=char_budget)
    if payload is None:
        return None
    return HandoffResponse.model_validate(payload)


def build_trace_diff(
    conn: sqlite3.Connection,
    trace_id_a: str,
    trace_id_b: str,
    *,
    workspace_id: str | None = None,
) -> TraceDiffResponse | None:
    trace_a = TraceRepo.get(conn, trace_id_a)
    trace_b = TraceRepo.get(conn, trace_id_b)
    if trace_a is None or trace_b is None:
        return None
    if workspace_id is not None and (
        trace_a.workspace_id != workspace_id or trace_b.workspace_id != workspace_id
    ):
        return None
    payload = build_trace_diff_payload(conn, trace_id_a=trace_id_a, trace_id_b=trace_id_b)
    if payload is None:
        return None
    spans_a = SpanRepo.list_by_trace(conn, trace_id_a)
    spans_b = SpanRepo.list_by_trace(conn, trace_id_b)
    outcome_a = OutcomeRepo.get(conn, trace_id_a)
    outcome_b = OutcomeRepo.get(conn, trace_id_b)
    diagnostic_a = DiagnosticRepo.get(conn, trace_id_a)
    diagnostic_b = DiagnosticRepo.get(conn, trace_id_b)

    def total_tokens(trace: object) -> int:
        return sum(
            int(getattr(trace, field, 0) or 0)
            for field in (
                "input_tokens",
                "output_tokens",
                "cache_read_tokens",
                "cache_creation_tokens",
                "reasoning_tokens",
            )
        )

    tokens_a = total_tokens(trace_a)
    tokens_b = total_tokens(trace_b)
    duration_a = _duration_ms(trace_a.started_at, trace_a.ended_at)
    duration_b = _duration_ms(trace_b.started_at, trace_b.ended_at)
    delta_duration = (
        duration_b - duration_a if duration_a is not None and duration_b is not None else None
    )

    region_rows = conn.execute(
        """
        SELECT s.trace_id, cr.region, SUM(cr.tokens) AS tokens, SUM(cr.cost) AS cost
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        WHERE s.trace_id IN (?, ?)
        GROUP BY s.trace_id, cr.region
        ORDER BY cr.region
        """,
        (trace_id_a, trace_id_b),
    ).fetchall()
    region_values: dict[str, dict[str, tuple[int, float]]] = defaultdict(dict)
    for row in region_rows:
        region_values[str(row["region"])][str(row["trace_id"])] = (
            int(row["tokens"] or 0),
            float(row["cost"] or 0.0),
        )
    regions: list[TraceDiffRegion] = []
    for region in sorted(region_values):
        a_tokens, a_cost = region_values[region].get(trace_id_a, (0, 0.0))
        b_tokens, b_cost = region_values[region].get(trace_id_b, (0, 0.0))
        regions.append(
            TraceDiffRegion(
                region=region,
                tokens_a=a_tokens,
                tokens_b=b_tokens,
                delta_tokens=b_tokens - a_tokens,
                cost_a=a_cost,
                cost_b=b_cost,
                delta_cost=b_cost - a_cost,
            )
        )

    reasons: list[str] = []
    facts: list[str] = []
    not_comparable = False
    if trace_a.source != trace_b.source:
        reasons.append("Sources differ, so capture semantics and coverage may differ.")
        not_comparable = True
    else:
        facts.append("Both sessions use the same recorded source adapter.")
    if trace_a.project and trace_b.project and trace_a.project != trace_b.project:
        reasons.append("Recorded projects differ; task and environment equivalence is not known.")
        not_comparable = True
    elif trace_a.project and trace_b.project:
        facts.append("Both sessions have the same recorded project.")
    else:
        reasons.append("Project identity is missing on at least one session.")
    if (
        trace_a.difficulty_bucket
        and trace_b.difficulty_bucket
        and trace_a.difficulty_bucket != trace_b.difficulty_bucket
    ):
        reasons.append("Difficulty buckets differ.")
    elif trace_a.difficulty_bucket and trace_b.difficulty_bucket:
        facts.append("Recorded difficulty buckets match.")
    else:
        reasons.append("Difficulty comparability is unavailable for at least one session.")
    if trace_a.title and trace_b.title and trace_a.title != trace_b.title:
        reasons.append("Recorded task titles differ; equivalent intent is not established.")
    elif trace_a.title and trace_b.title:
        facts.append("Recorded task titles match.")
    else:
        reasons.append("Task-title comparability is unavailable.")
    comparability_state: Literal["comparable", "limited", "not_comparable"]
    if not_comparable:
        comparability_state = "not_comparable"
    elif reasons:
        comparability_state = "limited"
    else:
        comparability_state = "comparable"
    comparability = TraceDiffComparability(
        state=comparability_state,
        reasons=reasons,
        facts=facts,
        limitation=(
            "Deltas are descriptive associations between two recorded sessions. They do not "
            "establish that a model, prompt, rule, or tool caused the difference."
        ),
    )

    session_a = TraceDiffEvidence(
        side="a", label="Open session A", trace_id=trace_id_a, evidence_type="session"
    )
    session_b = TraceDiffEvidence(
        side="b", label="Open session B", trace_id=trace_id_b, evidence_type="session"
    )
    evidence: list[TraceDiffEvidence] = [session_a, session_b]
    diagnostic_sides: tuple[
        tuple[Literal["a", "b"], str, Diagnostic | None],
        tuple[Literal["a", "b"], str, Diagnostic | None],
    ] = (
        ("a", trace_id_a, diagnostic_a),
        ("b", trace_id_b, diagnostic_b),
    )
    for side, trace_id, diagnostic in diagnostic_sides:
        if diagnostic is not None and diagnostic.failure_origin_span_id:
            evidence.append(
                TraceDiffEvidence(
                    side=side,
                    label=f"Open {side.upper()} failure origin",
                    trace_id=trace_id,
                    span_id=diagnostic.failure_origin_span_id,
                    evidence_type="diagnostic",
                )
            )

    changes: list[TraceDiffChange] = []

    def signed_statement(metric: str, delta: float, unit: str) -> str:
        direction = "increased" if delta > 0 else "decreased" if delta < 0 else "did not change"
        magnitude = abs(delta)
        return f"Recorded {metric} {direction} by {magnitude:g}{unit}."

    changes.append(
        TraceDiffChange(
            statement=signed_statement("total tokens", tokens_b - tokens_a, " tokens"),
            basis="recorded_delta",
            evidence=[session_a, session_b],
        )
    )
    changes.append(
        TraceDiffChange(
            statement=signed_statement("cost", trace_b.cost - trace_a.cost, " USD"),
            basis="recorded_delta",
            evidence=[session_a, session_b],
        )
    )
    label_a = outcome_a.outcome_label if outcome_a is not None else None
    label_b = outcome_b.outcome_label if outcome_b is not None else None
    if label_a != label_b:
        changes.append(
            TraceDiffChange(
                statement=(
                    f"Recorded outcome changed from {label_a or 'unavailable'} "
                    f"to {label_b or 'unavailable'}."
                ),
                basis="recorded_delta",
                evidence=[session_a, session_b],
            )
        )
    diagnostic_label_a = diagnostic_a.primary_category if diagnostic_a is not None else None
    diagnostic_label_b = diagnostic_b.primary_category if diagnostic_b is not None else None
    if diagnostic_label_a != diagnostic_label_b:
        diagnostic_evidence = [item for item in evidence if item.evidence_type == "diagnostic"] or [
            session_a,
            session_b,
        ]
        changes.append(
            TraceDiffChange(
                statement=(
                    f"Recorded diagnostic category changed from "
                    f"{diagnostic_label_a or 'unavailable'} to "
                    f"{diagnostic_label_b or 'unavailable'}."
                ),
                basis="diagnostic",
                evidence=diagnostic_evidence,
            )
        )
    changes.append(
        TraceDiffChange(
            statement=comparability.limitation,
            basis="limitation",
            evidence=[session_a, session_b],
        )
    )

    models_a = sorted(
        {model for model in [trace_a.model, *(span.model for span in spans_a)] if model}
    )
    models_b = sorted(
        {model for model in [trace_b.model, *(span.model for span in spans_b)] if model}
    )
    payload["analysis"] = TraceDiffAnalysis(
        tokens_a=tokens_a,
        tokens_b=tokens_b,
        delta_tokens=tokens_b - tokens_a,
        duration_ms_a=duration_a,
        duration_ms_b=duration_b,
        delta_duration_ms=delta_duration,
        models_a=models_a,
        models_b=models_b,
        regions=regions,
        outcome_a=outcome_a,
        outcome_b=outcome_b,
        diagnostic_a=diagnostic_a,
        diagnostic_b=diagnostic_b,
        alignment_mode=(
            "lcs"
            if min(len(spans_a), MAX_DIFF_SPANS_PER_SIDE)
            * min(len(spans_b), MAX_DIFF_SPANS_PER_SIDE)
            <= MAX_LCS_CELLS
            else "bounded_position"
        ),
        alignment_truncated=(
            len(spans_a) > MAX_DIFF_SPANS_PER_SIDE or len(spans_b) > MAX_DIFF_SPANS_PER_SIDE
        ),
        alignment_limitation=(
            f"Turn alignment is limited to the first {MAX_DIFF_SPANS_PER_SIDE} spans per session."
            if len(spans_a) > MAX_DIFF_SPANS_PER_SIDE or len(spans_b) > MAX_DIFF_SPANS_PER_SIDE
            else (
                "Large sequences use deterministic position alignment instead of quadratic LCS."
                if len(spans_a) * len(spans_b) > MAX_LCS_CELLS
                else None
            )
        ),
        comparability=comparability,
        what_changed=changes,
        evidence=evidence,
    ).model_dump(mode="json")
    return TraceDiffResponse.model_validate(payload)


def _replay_summary(
    trace: object,
    spans: list[Span],
    seq: int,
    *,
    all_spans: list[Span],
) -> ReplaySummary:
    context = next(
        (span.context_tokens_after for span in reversed(spans) if span.context_tokens_after),
        None,
    )
    files = len({span.path_rel for span in spans if span.path_rel})
    agents = len({span.agent_id for span in spans if span.agent_id})
    final_cost = float(getattr(trace, "cost", 0.0) or 0.0)
    all_tokens = sum((span.input_tokens or 0) + (span.output_tokens or 0) for span in all_spans)
    visible_tokens = sum((span.input_tokens or 0) + (span.output_tokens or 0) for span in spans)
    progress = visible_tokens / all_tokens if all_tokens else len(spans) / max(1, len(all_spans))
    return ReplaySummary(
        turn=seq,
        context_tokens=context,
        cost=round(final_cost * min(1.0, progress), 8),
        cost_estimated=len(spans) < len(all_spans),
        files_read=files,
        agents=agents,
    )


def build_replay(conn: sqlite3.Connection, trace_id: str, seq: int) -> ReplayResponse | None:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    all_spans = SpanRepo.list_by_trace(conn, trace_id)
    spans = [span for span in all_spans if span.seq <= seq]
    return ReplayResponse(
        trace_id=trace_id,
        seq=seq,
        spans=spans,
        summary=_replay_summary(trace, spans, seq, all_spans=all_spans),
    )


def build_replay_checkpoints(conn: sqlite3.Connection, trace_id: str) -> ReplayResponse | None:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    all_spans = SpanRepo.list_by_trace(conn, trace_id)
    if not all_spans:
        return ReplayResponse(trace_id=trace_id, max_seq=0, step=1, checkpoints=[])
    max_seq = max(span.seq for span in all_spans)
    checkpoint_count = max(
        1,
        min(MAX_REPLAY_CHECKPOINTS, MAX_REPLAY_SERIALIZED_SPANS // len(all_spans)),
    )
    step = max(1, (max_seq + checkpoint_count - 1) // checkpoint_count)
    checkpoints: list[ReplayCheckpoint] = []
    for seq in range(step, max_seq + step, step):
        capped = min(seq, max_seq)
        spans = [span for span in all_spans if span.seq <= capped]
        checkpoints.append(
            ReplayCheckpoint(
                seq=capped,
                spans=spans,
                summary=_replay_summary(trace, spans, capped, all_spans=all_spans),
            )
        )
    if not checkpoints or checkpoints[-1].seq != max_seq:
        checkpoints.append(
            ReplayCheckpoint(
                seq=max_seq,
                spans=all_spans,
                summary=_replay_summary(trace, all_spans, max_seq, all_spans=all_spans),
            )
        )
    return ReplayResponse(
        trace_id=trace_id,
        max_seq=max_seq,
        step=step,
        checkpoints=checkpoints,
    )
