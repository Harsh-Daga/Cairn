"""Build §6.2 API payloads from store repositories."""

from __future__ import annotations

import shlex
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from server.analyze.diff import build_trace_diff_payload
from server.analyze.fingerprint import FINGERPRINT_AXIS_LABELS
from server.analyze.fingerprint_math import (
    MIN_JOINT_BASELINE,
    detect_drift,
    detect_gradual_drift,
)
from server.analyze.gauge import compute_gauge
from server.analyze.tail import expected_worst
from server.api.schemas import (
    AgentAggregate,
    AgentsResponse,
    BehaviorResponse,
    BehaviorSeriesPoint,
    DataNote,
    DriftEvent,
    EvidenceChainResponse,
    ExperimentDetailResponse,
    ExperimentRow,
    ExperimentsResponse,
    InsightRow,
    InsightsResponse,
    McpConsultation,
    MoneySummary,
    NarrativeSentence,
    OverviewResponse,
    PlanWindowGauge,
    QualityResponse,
    QualityTrend,
    RecapResponse,
    RecapVerdict,
    RegionsAnalyticsResponse,
    ReplayCheckpoint,
    ReplayResponse,
    SearchHit,
    SearchResponse,
    SpanLink,
    SpanNode,
    TailAnalyticsResponse,
    TailRisk,
    TraceDetailResponse,
    TraceDiffResponse,
    TraceRow,
    TracesListResponse,
    UsageAnalyticsResponse,
    UsageSeriesPoint,
    WasteAnalyticsResponse,
    WasteCategory,
    WasteCause,
    WorkspaceAdapter,
    WorkspaceResponse,
)
from server.improve.experiments import preview as experiment_preview
from server.models.fingerprint import Fingerprint
from server.models.span import Span
from server.store.migrate import FTS_AVAILABLE
from server.store.repos.data_quality import DataQualityRepo
from server.store.repos.diagnostics import DiagnosticRepo
from server.store.repos.evidence import EvidenceRepo
from server.store.repos.experiments import ExperimentRepo
from server.store.repos.fingerprints import FingerprintRepo
from server.store.repos.ingest_cursors import IngestCursorRepo
from server.store.repos.insights import InsightRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.rollup import RollupRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceListFilters, TraceRepo
from server.store.repos.workspaces import WorkspaceRepo


def _since_iso(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


def _trace_row(trace: Any) -> TraceRow:
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
    )


def _data_notes(conn: sqlite3.Connection, *, workspace_id: str, since: str) -> list[DataNote]:
    notes: list[DataNote] = []
    rows = conn.execute(
        """
        SELECT source, COUNT(*) AS n
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND cost_source = 'absent'
        GROUP BY source
        """,
        (workspace_id, since),
    ).fetchall()
    for row in rows:
        source = str(row["source"])
        n = int(row["n"])
        notes.append(
            DataNote(
                source=source,
                sessions=n,
                issue="no_cost_data",
                message=f"{n} {source} trace(s) have no reliable cost/token data.",
            )
        )
    return notes


_WASTE_GUIDANCE: dict[str, tuple[str, str]] = {
    "identical_call": (
        "The agent repeated an identical tool call after other work without new inputs.",
        "Add an instruction to reuse the previous result unless the underlying input changed.",
    ),
    "blind_retry": (
        "The agent retried the same operation before using the failure output.",
        "Require the agent to explain the error and change one input before retrying.",
    ),
    "retry_loop": (
        "A failing tool was rerun repeatedly with no effective correction.",
        "Add a retry limit and require a different diagnostic step after the first failure.",
    ),
    "oversize_result": (
        "Large tool output consumed context beyond the useful working set.",
        "Ask for bounded output with a line, result, or file limit.",
    ),
    "stale_context": (
        "An unchanged file was read again after it was already in context.",
        "Tell the agent to reuse its prior summary until the file changes.",
    ),
    "orientation_waste": (
        "Early exploration read broadly without moving toward an edit.",
        "Start with the named files and stop exploring once the change surface is known.",
    ),
    "uncleared_tool_result": (
        "Re-fetchable tool output stayed in context after it stopped being useful.",
        "Summarize large results and discard the raw output before continuing.",
    ),
    "context_rot": (
        "Work continued after the context window entered its high-degradation tail.",
        "Checkpoint the plan and start a fresh session before context saturation.",
    ),
    "rebilling_waste": (
        "Previously supplied context was billed again in later model calls.",
        "Keep stable instructions concise and move large references behind targeted reads.",
    ),
}


def _money_summary(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    since: str,
    days: int,
) -> MoneySummary:
    traces = conn.execute(
        """
        SELECT trace_id, input_tokens, output_tokens, cost, cost_source, waste_tokens
        FROM traces
        WHERE workspace_id = ? AND (started_at IS NULL OR started_at >= ?)
        """,
        (workspace_id, since),
    ).fetchall()
    category_rows = conn.execute(
        """
        SELECT s.trace_id, s.waste_category, SUM(s.waste_tokens) AS waste_tokens
        FROM spans s JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND (t.started_at IS NULL OR t.started_at >= ?)
          AND s.waste_category IS NOT NULL AND s.waste_tokens > 0
        GROUP BY s.trace_id, s.waste_category
        """,
        (workspace_id, since),
    ).fetchall()
    by_trace: dict[str, dict[str, int]] = defaultdict(dict)
    for category_row in category_rows:
        by_trace[str(category_row["trace_id"])][str(category_row["waste_category"])] = int(
            category_row["waste_tokens"] or 0
        )

    category_tokens: dict[str, int] = defaultdict(int)
    category_cost: dict[str, float] = defaultdict(float)
    total_spend = 0.0
    wasted_spend = 0.0
    spend_estimated = False
    for trace in traces:
        cost = float(trace["cost"] or 0.0)
        total_spend += cost
        spend_estimated = spend_estimated or trace["cost_source"] == "priced"
        tokens = int(trace["input_tokens"] or 0) + int(trace["output_tokens"] or 0)
        waste_tokens = int(trace["waste_tokens"] or 0)
        if tokens <= 0 or waste_tokens <= 0 or cost <= 0:
            continue
        priced_waste_tokens = min(tokens, waste_tokens)
        trace_waste_cost = cost * priced_waste_tokens / tokens
        wasted_spend += trace_waste_cost
        categories = dict(by_trace.get(str(trace["trace_id"]), {}))
        attributed = sum(categories.values())
        if waste_tokens > attributed:
            categories["rebilling_waste"] = categories.get("rebilling_waste", 0) + (
                waste_tokens - attributed
            )
        scale = priced_waste_tokens / max(1, sum(categories.values()))
        for category, raw_tokens in categories.items():
            allocated_tokens = int(round(raw_tokens * scale))
            category_tokens[category] += allocated_tokens
            category_cost[category] += (
                trace_waste_cost * raw_tokens / max(1, sum(categories.values()))
            )

    causes: list[WasteCause] = []
    ranked_categories = sorted(category_cost.items(), key=lambda item: item[1], reverse=True)[:3]
    for category, amount in ranked_categories:
        cause, fix = _WASTE_GUIDANCE.get(
            category,
            (
                "Cairn detected avoidable context use in this category.",
                "Review the supporting sessions and add a targeted instruction for this pattern.",
            ),
        )
        causes.append(
            WasteCause(
                category=category,
                waste_tokens=category_tokens[category],
                estimated_savings_usd=round(amount, 4),
                cause=cause,
                fix=fix,
            )
        )
    return MoneySummary(
        period_days=days,
        total_spend_usd=round(total_spend, 4),
        spend_estimated=spend_estimated,
        wasted_spend_usd=round(wasted_spend, 4),
        wasted_spend_pct=round((wasted_spend / total_spend * 100) if total_spend else 0.0, 2),
        waste_estimated=wasted_spend > 0,
        top_causes=causes,
        primary_action="/optimize",
    )


def build_overview(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
) -> OverviewResponse:
    since = _since_iso(days)
    row = conn.execute(
        """
        SELECT
          COUNT(*) AS traces,
          COALESCE(SUM(input_tokens), 0) AS input_tokens,
          COALESCE(SUM(output_tokens), 0) AS output_tokens,
          COALESCE(SUM(cost), 0) AS cost,
          COALESCE(SUM(waste_tokens), 0) AS waste_tokens
        FROM traces
        WHERE workspace_id = ? AND (started_at IS NULL OR started_at >= ?)
        """,
        (workspace_id, since),
    ).fetchone()
    traces = int(row["traces"] or 0) if row else 0
    cost = float(row["cost"] or 0.0) if row else 0.0
    waste = int(row["waste_tokens"] or 0) if row else 0
    kpis: dict[str, float | int | None] = {
        "traces": traces,
        "input_tokens": int(row["input_tokens"] or 0) if row else 0,
        "output_tokens": int(row["output_tokens"] or 0) if row else 0,
        "cost": cost,
        "waste_tokens": waste,
    }
    narrative: list[NarrativeSentence] = []
    if traces:
        narrative.append(
            NarrativeSentence(
                text=(
                    f"{traces} agent {'session' if traces == 1 else 'sessions'} "
                    f"in the last {days} days."
                ),
                filter={"days": str(days)},
            )
        )
    if cost > 0:
        narrative.append(NarrativeSentence(text=f"Total spend ${cost:.2f}."))
    if waste > 0:
        narrative.append(
            NarrativeSentence(
                text=f"Estimated {waste:,} waste tokens flagged.",
                filter={"view": "waste"},
            )
        )
    costs = [
        float(r["cost"] or 0.0)
        for r in conn.execute(
            """
            SELECT cost FROM traces
            WHERE workspace_id = ? AND started_at >= ? AND cost > 0
            """,
            (workspace_id, since),
        ).fetchall()
    ]
    tail = TailRisk()
    if len(costs) >= 5:
        arr = np.array(costs, dtype=float)
        threshold = float(np.quantile(arr, 0.9))
        exceedances = arr[arr > threshold] - threshold
        if exceedances.size >= 5:
            tail = TailRisk(
                expected_worst_cost=expected_worst(exceedances, 7),
                exceedance_count=int(exceedances.size),
                threshold=threshold,
            )
    return OverviewResponse(
        days=days,
        kpis=kpis,
        money=_money_summary(conn, workspace_id=workspace_id, since=since, days=days),
        narrative=narrative,
        tail_risk=tail,
        data_notes=_data_notes(conn, workspace_id=workspace_id, since=since),
    )


def build_recap(conn: sqlite3.Connection, *, workspace_id: str) -> RecapResponse:
    """Build a bounded seven-day return summary from local ledger data."""
    now = datetime.now(UTC)
    since = (now - timedelta(days=7)).isoformat()
    previous_since = (now - timedelta(days=14)).isoformat()
    quality_rows = conn.execute(
        """
        SELECT
          AVG(CASE WHEN t.started_at >= ? THEN o.quality_score END) AS current_mean,
          COUNT(CASE WHEN t.started_at >= ? THEN 1 END) AS current_n,
          AVG(CASE WHEN t.started_at >= ? AND t.started_at < ? THEN o.quality_score END)
            AS previous_mean,
          COUNT(CASE WHEN t.started_at >= ? AND t.started_at < ? THEN 1 END) AS previous_n
        FROM outcomes o JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ? AND o.quality_score IS NOT NULL AND t.started_at >= ?
        """,
        (
            since,
            since,
            previous_since,
            since,
            previous_since,
            since,
            workspace_id,
            previous_since,
        ),
    ).fetchone()
    current_mean = (
        float(quality_rows["current_mean"])
        if quality_rows["current_mean"] is not None
        else None
    )
    previous_mean = (
        float(quality_rows["previous_mean"])
        if quality_rows["previous_mean"] is not None
        else None
    )
    delta = (
        round(current_mean - previous_mean, 2)
        if current_mean is not None and previous_mean is not None
        else None
    )
    verdict_rows = conn.execute(
        """
        SELECT experiment_id, verdict, effect_estimate, effect_ci_low, effect_ci_high, measured_at
        FROM experiments
        WHERE status = 'verdict' AND verdict IS NOT NULL AND measured_at >= ?
        ORDER BY measured_at DESC
        """,
        (since,),
    ).fetchall()
    return RecapResponse(
        generated_at=now.isoformat(),
        period_days=7,
        money=_money_summary(conn, workspace_id=workspace_id, since=since, days=7),
        quality_trend=QualityTrend(
            current_mean=round(current_mean, 2) if current_mean is not None else None,
            previous_mean=round(previous_mean, 2) if previous_mean is not None else None,
            delta=delta,
            current_sessions=int(quality_rows["current_n"] or 0),
            previous_sessions=int(quality_rows["previous_n"] or 0),
        ),
        experiment_verdicts=[
            RecapVerdict(
                experiment_id=str(row["experiment_id"]),
                verdict=str(row["verdict"]),
                effect_estimate=(
                    float(row["effect_estimate"]) if row["effect_estimate"] is not None else None
                ),
                effect_ci_low=(
                    float(row["effect_ci_low"]) if row["effect_ci_low"] is not None else None
                ),
                effect_ci_high=(
                    float(row["effect_ci_high"]) if row["effect_ci_high"] is not None else None
                ),
                measured_at=str(row["measured_at"]),
            )
            for row in verdict_rows
        ],
    )


def build_traces_list(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int | None = None,
    source: str | None = None,
    project: str | None = None,
    actor: str | None = None,
    agent: str | None = None,
    q: str | None = None,
    sort: str = "recent",
    limit: int = 50,
    offset: int = 0,
) -> TracesListResponse:
    filters = TraceListFilters(
        workspace_id=workspace_id,
        days=days,
        source=source,
        project=project,
        actor=actor,
        agent=agent,
        q=q,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    traces = TraceRepo.list(conn, filters)
    total = TraceRepo.count(conn, filters)
    return TracesListResponse(
        traces=[_trace_row(t) for t in traces],
        total=total,
        limit=limit,
        offset=offset,
    )


def _build_span_tree(spans: list[Span]) -> list[SpanNode]:
    by_id = {s.span_id: SpanNode(span=s) for s in spans}
    roots: list[SpanNode] = []
    for node in by_id.values():
        parent_id = node.span.parent_span_id
        if parent_id and parent_id in by_id:
            by_id[parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


def build_trace_detail(conn: sqlite3.Connection, trace_id: str) -> TraceDetailResponse | None:
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
            from_span_id=str(r["from_span_id"]),
            to_span_id=str(r["to_span_id"]),
            link_type=str(r["link_type"]),
        )
        for r in link_rows
    ]
    region_rows = conn.execute(
        """
        SELECT span_id, region, tokens, cost, content_hash
        FROM context_regions
        WHERE span_id IN (SELECT span_id FROM spans WHERE trace_id = ?)
        """,
        (trace_id,),
    ).fetchall()
    regions = [dict(r) for r in region_rows]
    consultation_rows = conn.execute(
        """SELECT event_id, trace_id, after_seq, tool_name, called_at
           FROM mcp_consultations
           WHERE trace_id = ?
           ORDER BY after_seq, called_at""",
        (trace_id,),
    ).fetchall()
    consultations = [McpConsultation.model_validate(dict(row)) for row in consultation_rows]
    diag = DiagnosticRepo.get(conn, trace_id)
    quality = DataQualityRepo.get(conn, trace_id)
    outcome = OutcomeRepo.get(conn, trace_id)
    return TraceDetailResponse(
        trace=trace,
        spans=spans,
        tree=_build_span_tree(spans),
        links=links,
        mcp_consultations=consultations,
        regions=regions,
        diagnostics=diag.model_dump() if diag else None,
        quality=quality.model_dump() if quality else None,
        outcome=outcome.model_dump() if outcome else None,
    )


def build_trace_diff(
    conn: sqlite3.Connection, trace_id_a: str, trace_id_b: str
) -> TraceDiffResponse | None:
    payload = build_trace_diff_payload(conn, trace_id_a=trace_id_a, trace_id_b=trace_id_b)
    if payload is None:
        return None
    return TraceDiffResponse.model_validate(payload)


def _replay_summary(
    trace: object,
    spans: list[Span],
    seq: int,
    *,
    all_spans: list[Span],
) -> dict[str, Any]:
    ctx = next(
        (s.context_tokens_after for s in reversed(spans) if s.context_tokens_after),
        None,
    )
    files = len({s.path_rel for s in spans if s.path_rel})
    agents = len({s.agent_id for s in spans if s.agent_id})
    final_cost = float(getattr(trace, "cost", 0.0) or 0.0)
    all_tokens = sum((s.input_tokens or 0) + (s.output_tokens or 0) for s in all_spans)
    visible_tokens = sum((s.input_tokens or 0) + (s.output_tokens or 0) for s in spans)
    progress = visible_tokens / all_tokens if all_tokens else len(spans) / max(1, len(all_spans))
    cost = round(final_cost * min(1.0, progress), 8)
    return {
        "turn": seq,
        "context_tokens": ctx,
        "cost": cost,
        "cost_estimated": len(spans) < len(all_spans),
        "files_read": files,
        "agents": agents,
    }


def build_replay(conn: sqlite3.Connection, trace_id: str, seq: int) -> ReplayResponse | None:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    all_spans = SpanRepo.list_by_trace(conn, trace_id)
    spans = [s for s in all_spans if s.seq <= seq]
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
    max_seq = max(s.seq for s in all_spans)
    step = max(1, (max_seq + 39) // 40)
    checkpoints: list[ReplayCheckpoint] = []
    for seq in range(step, max_seq + step, step):
        capped = min(seq, max_seq)
        spans = [s for s in all_spans if s.seq <= capped]
        checkpoints.append(
            ReplayCheckpoint(
                seq=capped,
                spans=spans,
                summary=_replay_summary(trace, spans, capped, all_spans=all_spans),
            )
        )
    if not checkpoints or checkpoints[-1].seq != max_seq:
        spans = all_spans
        checkpoints.append(
            ReplayCheckpoint(
                seq=max_seq,
                spans=spans,
                summary=_replay_summary(trace, spans, max_seq, all_spans=all_spans),
            )
        )
    return ReplayResponse(
        trace_id=trace_id,
        max_seq=max_seq,
        step=step,
        checkpoints=checkpoints,
    )


def build_agents(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
) -> AgentsResponse:
    since = _since_iso(days)
    rows = conn.execute(
        """
        WITH agent_trace AS (
          SELECT s.trace_id, s.agent_id, t.actor_id, a.display_name AS actor_name, t.cost,
                 SUM(COALESCE(s.input_tokens, 0)) AS input_tokens,
                 SUM(COALESCE(s.output_tokens, 0)) AS output_tokens,
                 SUM(COALESCE(s.input_tokens, 0) + COALESCE(s.output_tokens, 0)) AS agent_tokens
          FROM spans s
          JOIN traces t ON t.trace_id = s.trace_id
          LEFT JOIN actors a ON a.actor_id = t.actor_id
          WHERE t.workspace_id = ? AND (t.started_at IS NULL OR t.started_at >= ?)
          GROUP BY s.trace_id, s.agent_id, t.actor_id, a.display_name
        ), attributed AS (
          SELECT *, SUM(agent_tokens) OVER (PARTITION BY trace_id) AS trace_span_tokens,
                    COUNT(*) OVER (PARTITION BY trace_id) AS trace_agents
          FROM agent_trace
        )
        SELECT agent_id, actor_id, actor_name, COUNT(*) AS traces,
               SUM(input_tokens) AS input_tokens,
               SUM(output_tokens) AS output_tokens,
               SUM(CASE WHEN trace_span_tokens > 0
                        THEN cost * agent_tokens / trace_span_tokens
                        ELSE cost / trace_agents END) AS cost
        FROM attributed
        GROUP BY agent_id, actor_id, actor_name
        ORDER BY cost DESC
        """,
        (workspace_id, since),
    ).fetchall()
    agents = [
        AgentAggregate(
            agent_id=row["agent_id"],
            actor_id=row["actor_id"],
            actor_name=row["actor_name"],
            traces=int(row["traces"] or 0),
            input_tokens=int(row["input_tokens"] or 0),
            output_tokens=int(row["output_tokens"] or 0),
            cost=float(row["cost"] or 0.0),
        )
        for row in rows
    ]
    handoffs = conn.execute(
        """
        SELECT sl.from_span_id, sl.to_span_id, sl.link_type,
               s1.agent_id AS from_agent, s2.agent_id AS to_agent
        FROM span_links sl
        JOIN spans s1 ON s1.span_id = sl.from_span_id
        JOIN spans s2 ON s2.span_id = sl.to_span_id
        JOIN traces t ON t.trace_id = s1.trace_id
        WHERE sl.link_type = 'handoff' AND t.workspace_id = ?
          AND (t.started_at IS NULL OR t.started_at >= ?)
        """,
        (workspace_id, since),
    ).fetchall()
    return AgentsResponse(
        days=days,
        agents=agents,
        handoff_matrix=[dict(r) for r in handoffs],
    )


def build_behavior(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
) -> BehaviorResponse:
    since = _since_iso(days)
    traces = TraceRepo.list(
        conn,
        TraceListFilters(workspace_id=workspace_id, days=days, limit=500),
    )
    series: list[BehaviorSeriesPoint] = []
    fingerprints: list[Fingerprint] = []
    for trace in traces:
        fp = FingerprintRepo.get(conn, trace.trace_id)
        if fp is None:
            continue
        fingerprints.append(fp)
        series.append(
            BehaviorSeriesPoint(
                trace_id=trace.trace_id,
                ts=trace.started_at,
                vector=fp.vector,
                project=trace.project,
                model=trace.model,
            )
        )
    chronological = sorted(fingerprints, key=lambda fp: fp.ts or "")
    drift: list[DriftEvent] = []
    grouped: dict[tuple[str | None, str | None], list[Fingerprint]] = defaultdict(list)
    for fp in chronological:
        grouped[(fp.project, fp.model)].append(fp)
    strongest_baseline = 0
    for (project_name, model_name), group in grouped.items():
        if len(group) < 2:
            continue
        baseline = [fp.vector for fp in group[:-1]]
        strongest_baseline = max(strongest_baseline, len(baseline))
        result = detect_drift(group[-1].vector, baseline)
        if result.drift:
            drift.append(
                DriftEvent(
                    kind=result.kind,
                    trace_id=group[-1].trace_id,
                    project=project_name,
                    model=model_name,
                    distance=result.distance,
                    threshold=result.threshold,
                    per_dim_deltas=result.per_dim_deltas,
                )
            )
    weekly: dict[str, list[list[float]]] = defaultdict(list)
    for fp in chronological:
        if fp.week:
            weekly[fp.week].append(fp.vector)
    weekly_means = [
        (week, np.mean(vectors, axis=0).tolist()) for week, vectors in sorted(weekly.items())
    ]
    gradual = detect_gradual_drift(weekly_means, FINGERPRINT_AXIS_LABELS)
    if gradual["drift"]:
        drift.append(DriftEvent.model_validate({"kind": "gradual", **gradual}))

    baselines = FingerprintRepo.list_baselines(conn, limit=20)
    radar = baselines[0].model_dump() if baselines else None
    if radar is None and chronological:
        reference = max(grouped.values(), key=len)
        reference_mean = np.mean([fp.vector for fp in reference], axis=0).tolist()
        radar = {
            "project": reference[-1].project or "(unknown)",
            "model": reference[-1].model or "(unknown)",
            "week": "selected window",
            "mean_vector": reference_mean,
            "cov_inv": [],
            "n": len(reference),
        }
    if radar is not None:
        radar["axes"] = [
            {"axis": label, "value": abs(float(value))}
            for label, value in zip(FINGERPRINT_AXIS_LABELS, radar["mean_vector"], strict=False)
        ][:6]
    series.sort(key=lambda row: row.ts or "")
    return BehaviorResponse(
        days=days,
        series=series,
        drift=drift,
        radar=radar,
        baseline_progress={
            "collected": min(strongest_baseline, MIN_JOINT_BASELINE),
            "required": MIN_JOINT_BASELINE,
            "ready": strongest_baseline >= MIN_JOINT_BASELINE,
            "note": (
                f"{min(strongest_baseline, MIN_JOINT_BASELINE)}/{MIN_JOINT_BASELINE} "
                "sessions collected"
            ),
        },
        data_notes=_data_notes(conn, workspace_id=workspace_id, since=since),
    )


def build_quality(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
) -> QualityResponse:
    since = _since_iso(days)
    traces = TraceRepo.list(
        conn,
        TraceListFilters(workspace_id=workspace_id, days=days, limit=500),
    )
    outcomes: list[dict[str, Any]] = []
    scores: list[float] = []
    cps: list[dict[str, Any]] = []
    for trace in traces:
        outcome = OutcomeRepo.get(conn, trace.trace_id)
        if outcome is None:
            continue
        row = outcome.model_dump()
        row["trace_id"] = trace.trace_id
        row["cost"] = trace.cost
        outcomes.append(row)
        if outcome.quality_score is not None:
            scores.append(outcome.quality_score)
        if outcome.cost_per_success is not None:
            cps.append(
                {
                    "trace_id": trace.trace_id,
                    "day": (trace.started_at or "")[:10],
                    "cost_per_success": outcome.cost_per_success,
                }
            )
    histogram: list[dict[str, Any]] = []
    if scores:
        buckets = [0, 25, 50, 75, 100]
        for lo, hi in zip(buckets, buckets[1:], strict=False):
            count = sum(1 for score in scores if lo <= score < hi or (hi == 100 and score == 100))
            histogram.append({"bucket": f"{lo}-{hi}", "count": count})
    return QualityResponse(
        days=days,
        outcomes=outcomes,
        histogram=histogram,
        cost_per_success=cps,
        data_notes=_data_notes(conn, workspace_id=workspace_id, since=since),
    )


def build_usage_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    group_by: str = "day",
) -> UsageAnalyticsResponse:
    rollups = RollupRepo.list_by_workspace(conn, workspace_id, days=days)
    series_map: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "waste_tokens": 0,
            "cost": 0.0,
            "traces": 0,
        }
    )
    for row in rollups:
        if group_by == "day":
            key = row.day
        elif group_by == "model":
            key = row.model or "(unknown)"
        elif group_by == "source":
            key = row.source
        elif group_by == "project":
            key = row.project or "(unknown)"
        else:
            key = row.day
        bucket = series_map[key]
        bucket["input_tokens"] = int(bucket["input_tokens"]) + row.input_tokens
        bucket["output_tokens"] = int(bucket["output_tokens"]) + row.output_tokens
        bucket["waste_tokens"] = int(bucket["waste_tokens"]) + row.waste_tokens
        bucket["cost"] = float(bucket["cost"]) + row.cost
        bucket["traces"] = int(bucket["traces"]) + row.traces
    series = [
        UsageSeriesPoint(
            key=key,
            input_tokens=int(values["input_tokens"]),
            output_tokens=int(values["output_tokens"]),
            waste_tokens=int(values["waste_tokens"]),
            cost=float(values["cost"]),
            traces=int(values["traces"]),
        )
        for key, values in sorted(series_map.items())
    ]
    return UsageAnalyticsResponse(days=days, group_by=group_by, series=series)


def build_regions_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
) -> RegionsAnalyticsResponse:
    since = _since_iso(days)
    rows = conn.execute(
        """
        SELECT cr.region, SUM(cr.tokens) AS tokens, COUNT(*) AS spans
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ?
        GROUP BY cr.region
        ORDER BY tokens DESC
        """,
        (workspace_id, since),
    ).fetchall()
    return RegionsAnalyticsResponse(
        days=days,
        regions=[{"region": r["region"], "tokens": r["tokens"], "spans": r["spans"]} for r in rows],
    )


def build_waste_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
) -> WasteAnalyticsResponse:
    since = _since_iso(days)
    rows = conn.execute(
        """
        SELECT s.waste_category AS category, SUM(s.waste_tokens) AS tokens, COUNT(*) AS events
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND (t.started_at IS NULL OR t.started_at >= ?)
          AND s.waste_category IS NOT NULL
        GROUP BY s.waste_category
        ORDER BY tokens DESC
        """,
        (workspace_id, since),
    ).fetchall()
    categories = [
        WasteCategory(
            category=str(r["category"]),
            tokens=int(r["tokens"] or 0),
            events=int(r["events"] or 0),
        )
        for r in rows
        if r["category"]
    ]
    categorized_total = sum(category.tokens for category in categories)
    trace_waste_row = conn.execute(
        """
        SELECT COALESCE(SUM(waste_tokens), 0) AS tokens
        FROM traces
        WHERE workspace_id = ? AND (started_at IS NULL OR started_at >= ?)
        """,
        (workspace_id, since),
    ).fetchone()
    trace_total = int(trace_waste_row["tokens"] or 0) if trace_waste_row else 0
    residual = max(0, trace_total - categorized_total)
    if residual:
        residual_row = conn.execute(
            """
            SELECT COUNT(*) AS events
            FROM traces t
            WHERE t.workspace_id = ? AND (t.started_at IS NULL OR t.started_at >= ?)
              AND t.waste_tokens > COALESCE((
                SELECT SUM(s.waste_tokens) FROM spans s WHERE s.trace_id = t.trace_id
              ), 0)
            """,
            (workspace_id, since),
        ).fetchone()
        categories.append(
            WasteCategory(
                category="other_detected",
                tokens=residual,
                events=int(residual_row["events"] or 0) if residual_row else 0,
            )
        )
    categories.sort(key=lambda category: category.tokens, reverse=True)
    return WasteAnalyticsResponse(
        days=days,
        categories=categories,
        total_waste_tokens=trace_total,
    )


def build_tail_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
) -> TailAnalyticsResponse:
    overview = build_overview(conn, workspace_id=workspace_id, days=days)
    since = _since_iso(days)
    costs = [
        float(r["cost"] or 0.0)
        for r in conn.execute(
            """
            SELECT cost FROM traces
            WHERE workspace_id = ? AND started_at >= ? AND cost > 0
            """,
            (workspace_id, since),
        ).fetchall()
    ]
    exceedances: list[float] = []
    if len(costs) >= 5:
        arr = np.array(costs, dtype=float)
        threshold = float(np.quantile(arr, 0.9))
        exceedances = [float(x - threshold) for x in arr if x > threshold]
    return TailAnalyticsResponse(
        days=days,
        tail_risk=overview.tail_risk,
        exceedances=exceedances,
    )


def build_insights(
    conn: sqlite3.Connection,
    *,
    state: str | None = None,
    limit: int = 100,
) -> InsightsResponse:
    from server.models.insight import InsightLifecycle

    lifecycle: InsightLifecycle | None = None
    if state is not None:
        lifecycle = state  # type: ignore[assignment]
    rows = InsightRepo.list_by_state(conn, lifecycle, limit=limit)
    insights: list[InsightRow] = []
    for row in rows:
        evidence = EvidenceRepo.get(conn, row.insight.evidence_id)
        contract_raw = evidence.metrics.get("insight_contract", {}) if evidence else {}
        contract = contract_raw if isinstance(contract_raw, dict) else {}
        fix_raw = contract.get("fix")
        fix = fix_raw if isinstance(fix_raw, dict) else {}
        if not fix.get("value"):
            fix = {
                "kind": "manual",
                "label": "Review supporting evidence",
                "value": row.insight.action or row.insight.body,
            }
        unavailable_reason = contract.get("savings_unavailable_reason")
        if row.insight.savings_estimate is None and not unavailable_reason:
            unavailable_reason = "Legacy insight without a defensible savings estimate."
        insights.append(
            InsightRow(
                insight_id=row.insight.insight_id,
                fingerprint=row.insight.fingerprint,
                detector=row.insight.detector,
                severity=row.insight.severity,
                title=row.insight.title,
                body=row.insight.body,
                state=row.state.state,
                savings_estimate=row.insight.savings_estimate,
                savings_unavailable_reason=(
                    str(unavailable_reason) if unavailable_reason else None
                ),
                fix={str(key): str(value) for key, value in fix.items()},
                diagnostic=bool(contract.get("diagnostic", not contract)),
                action=row.insight.action,
                last_seen_at=row.insight.last_seen_at,
            )
        )
    return InsightsResponse(insights=insights, total=InsightRepo.count_by_state(conn, lifecycle))


def build_evidence_chain(conn: sqlite3.Connection, insight_id: str) -> EvidenceChainResponse | None:
    insight = InsightRepo.get(conn, insight_id)
    if insight is None:
        return None
    evidence = EvidenceRepo.get(conn, insight.evidence_id)
    if evidence is None:
        return None
    spans: list[Span] = []
    if evidence.span_ids:
        for span_id in evidence.span_ids:
            span = SpanRepo.get(conn, span_id)
            if span is not None:
                spans.append(span)
    return EvidenceChainResponse(
        insight_id=insight_id,
        evidence_id=evidence.evidence_id,
        producer=evidence.producer,
        produced_at=evidence.produced_at,
        trace_ids=evidence.trace_ids,
        span_ids=evidence.span_ids,
        metrics=evidence.metrics,
        spans=spans,
    )


def build_experiments(conn: sqlite3.Connection) -> ExperimentsResponse:
    rows = ExperimentRepo.list_all(conn)
    experiments = [
        ExperimentRow(
            experiment_id=e.experiment_id,
            status=e.status,
            target_file=e.target_file,
            created_at=e.created_at,
            applied_at=e.applied_at,
            min_holdout=e.min_holdout,
            outcome_n_effective=e.outcome_n_effective,
            verdict=e.verdict,
            lift_pct=e.effect_estimate,
            effect_ci_low=e.effect_ci_low,
            effect_ci_high=e.effect_ci_high,
            measured_at=e.measured_at,
        )
        for e in rows
    ]
    return ExperimentsResponse(experiments=experiments)


def build_experiment_detail(
    conn: sqlite3.Connection,
    experiment_id: str,
    *,
    workspace_id: str,
) -> ExperimentDetailResponse | None:
    exp = ExperimentRepo.get(conn, experiment_id)
    if exp is None:
        return None
    preview_result = experiment_preview(conn, exp, workspace_id=workspace_id)
    return ExperimentDetailResponse(
        experiment=exp.model_dump(),
        preview={
            "expected_days_to_verdict": preview_result.expected_days_to_verdict,
            "traces_per_day": preview_result.traces_per_day,
            "n_effective_needed": preview_result.n_effective_needed,
            "traffic_unknown": preview_result.traffic_unknown,
        },
    )


def build_search(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    q: str,
    limit: int = 20,
) -> SearchResponse:
    if not q.strip():
        return SearchResponse(q=q, hits=[], total=0)

    terms: list[str] = []
    operators: dict[str, str] = {}
    try:
        tokens = shlex.split(q)
    except ValueError:
        tokens = q.split()
    for token in tokens:
        if ":" in token:
            key, value = token.split(":", 1)
            if key.lower() in {"tool", "source", "is"} and value:
                operators[key.lower()] = value.lower()
                continue
        terms.append(token)
    phrase = " ".join(terms).strip()
    like = f"%{phrase}%"
    source = operators.get("source")
    status = operators.get("is")
    tool = operators.get("tool")

    trace_clauses = ["workspace_id = ?"]
    trace_params: list[object] = [workspace_id]
    if phrase:
        trace_clauses.append(
            "(LOWER(COALESCE(title, '')) LIKE LOWER(?) "
            "OR LOWER(trace_id) LIKE LOWER(?) OR LOWER(COALESCE(project, '')) LIKE LOWER(?))"
        )
        trace_params.extend((like, like, like))
    if source:
        trace_clauses.append("LOWER(source) = ?")
        trace_params.append(source)
    if status:
        trace_clauses.append("LOWER(status) = ?")
        trace_params.append(status)
    title_rows = []
    if not tool:
        title_rows = conn.execute(
            f"""
            SELECT trace_id, title FROM traces
            WHERE {" AND ".join(trace_clauses)}
            ORDER BY started_at DESC
            """,
            trace_params,
        ).fetchall()

    hits: list[SearchHit] = []
    for row in title_rows:
        hits.append(
            SearchHit(
                trace_id=str(row["trace_id"]),
                span_id=None,
                title=row["title"],
                snippet=str(row["title"] or ""),
                kind="trace",
            )
        )

    span_clauses = ["t.workspace_id = ?"]
    span_params: list[object] = [workspace_id]
    if phrase:
        span_clauses.append(
            "(LOWER(COALESCE(s.text_inline, '')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(s.name, '')) LIKE LOWER(?) "
            "OR LOWER(COALESCE(s.path_rel, '')) LIKE LOWER(?))"
        )
        span_params.extend((like, like, like))
    if source:
        span_clauses.append("LOWER(t.source) = ?")
        span_params.append(source)
    if status:
        span_clauses.append("LOWER(s.status) = ?")
        span_params.append(status)
    if tool:
        span_clauses.append("s.kind = 'tool_call' AND LOWER(COALESCE(s.name, '')) LIKE ?")
        span_params.append(f"%{tool}%")
    span_rows = conn.execute(
        f"""
        SELECT s.trace_id, s.span_id, s.text_inline, s.name, s.path_rel
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE {" AND ".join(span_clauses)}
        ORDER BY COALESCE(s.started_at, t.started_at) DESC, s.seq DESC
        """,
        span_params,
    ).fetchall()
    for row in span_rows:
        snippet = row["text_inline"] or row["path_rel"] or row["name"] or ""
        hits.append(
            SearchHit(
                trace_id=str(row["trace_id"]),
                span_id=str(row["span_id"]),
                title=None,
                snippet=str(snippet)[:200],
                kind="span",
            )
        )
    return SearchResponse(q=q, hits=hits[:limit], total=len(hits))


def build_workspace(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    root_path: str,
) -> WorkspaceResponse:
    ws = WorkspaceRepo.get(conn, workspace_id)
    if ws is None:
        msg = "workspace not found"
        raise ValueError(msg)
    cursors = IngestCursorRepo.list_all(conn)
    by_source: dict[str, list[Any]] = defaultdict(list)
    for cursor in cursors:
        by_source[cursor.source].append(cursor)
    adapters = [
        WorkspaceAdapter(
            source=source,
            streams=len(items),
            cursor_updated_at=max((c.updated_at for c in items), default=None),
        )
        for source, items in sorted(by_source.items())
    ]
    trace_count = conn.execute(
        "SELECT COUNT(*) AS n FROM traces WHERE workspace_id = ?",
        (workspace_id,),
    ).fetchone()
    insight_count = conn.execute("SELECT COUNT(*) AS n FROM insights").fetchone()
    agreement_rows = conn.execute(
        """
        SELECT o.quality_score, o.human_label
        FROM outcomes o
        JOIN traces t ON t.trace_id = o.trace_id
        WHERE t.workspace_id = ? AND o.human_label IS NOT NULL
          AND o.quality_score IS NOT NULL
        """,
        (workspace_id,),
    ).fetchall()
    agreement_count = sum(
        1
        for row in agreement_rows
        if (float(row["quality_score"]) >= 50.0) == (str(row["human_label"]) == "up")
    )
    agreement_rate = agreement_count / len(agreement_rows) if agreement_rows else None
    raw_gauge = compute_gauge(Path(root_path)).as_dict()
    gauge: PlanWindowGauge | None = None
    if raw_gauge.get("total_tokens") or raw_gauge.get("limit") is not None:
        gauge = PlanWindowGauge(
            window_hours=int(raw_gauge.get("window_hours") or 5),
            total_tokens=int(raw_gauge.get("total_tokens") or 0),
            by_source={str(k): int(v) for k, v in (raw_gauge.get("by_source") or {}).items()},
            limit=raw_gauge.get("limit"),
            exceeded=bool(raw_gauge.get("exceeded")),
        )
    return WorkspaceResponse(
        workspace_id=workspace_id,
        root_path=root_path,
        name=ws.name,
        adapters=adapters,
        health={
            "trace_count": int(trace_count["n"] or 0) if trace_count else 0,
            "insight_count": int(insight_count["n"] or 0) if insight_count else 0,
            "fts_available": FTS_AVAILABLE,
            "human_label_agreement": {
                "labeled_sessions": len(agreement_rows),
                "agreements": agreement_count,
                "rate": agreement_rate,
            },
        },
        gauge=gauge,
    )
