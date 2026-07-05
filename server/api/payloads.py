"""Build §6.2 API payloads from store repositories."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from server.analyze.gauge import compute_gauge
from server.analyze.tail import expected_worst
from server.api.schemas import (
    AgentAggregate,
    AgentsResponse,
    BehaviorResponse,
    DataNote,
    EvidenceChainResponse,
    ExperimentDetailResponse,
    ExperimentRow,
    ExperimentsResponse,
    InsightRow,
    InsightsResponse,
    NarrativeSentence,
    OverviewResponse,
    PlanWindowGauge,
    QualityResponse,
    RegionsAnalyticsResponse,
    ReplayResponse,
    SearchHit,
    SearchResponse,
    SpanLink,
    SpanNode,
    TailAnalyticsResponse,
    TailRisk,
    TraceDetailResponse,
    TraceRow,
    TracesListResponse,
    UsageAnalyticsResponse,
    WasteAnalyticsResponse,
    WorkspaceAdapter,
    WorkspaceResponse,
)
from server.improve.experiments import preview as experiment_preview
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
                text=f"{traces} agent session(s) in the last {days} days.",
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
        narrative=narrative,
        tail_risk=tail,
        data_notes=_data_notes(conn, workspace_id=workspace_id, since=since),
    )


def build_traces_list(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int | None = None,
    source: str | None = None,
    project: str | None = None,
    actor: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> TracesListResponse:
    filters = TraceListFilters(
        workspace_id=workspace_id,
        days=days,
        source=source,
        project=project,
        actor=actor,
        limit=limit,
        offset=offset,
    )
    traces = TraceRepo.list(conn, filters)
    if q:
        needle = q.lower()
        traces = [
            t
            for t in traces
            if (t.title and needle in t.title.lower())
            or needle in t.trace_id.lower()
            or (t.project and needle in t.project.lower())
        ]
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
    diag = DiagnosticRepo.get(conn, trace_id)
    quality = DataQualityRepo.get(conn, trace_id)
    return TraceDetailResponse(
        trace=trace,
        spans=spans,
        tree=_build_span_tree(spans),
        links=links,
        regions=regions,
        diagnostics=diag.model_dump() if diag else None,
        quality=quality.model_dump() if quality else None,
    )


def build_replay(conn: sqlite3.Connection, trace_id: str, seq: int) -> ReplayResponse | None:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    spans = [s for s in SpanRepo.list_by_trace(conn, trace_id) if s.seq <= seq]
    ctx = next(
        (s.context_tokens_after for s in reversed(spans) if s.context_tokens_after),
        None,
    )
    files = len({s.path_rel for s in spans if s.path_rel})
    agents = len({s.agent_id for s in spans if s.agent_id})
    return ReplayResponse(
        trace_id=trace_id,
        seq=seq,
        spans=spans,
        summary={
            "turn": seq,
            "context_tokens": ctx,
            "cost": trace.cost,
            "files_read": files,
            "agents": agents,
        },
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
        SELECT s.agent_id, t.actor_id,
               COUNT(DISTINCT t.trace_id) AS traces,
               SUM(COALESCE(s.input_tokens, 0)) AS input_tokens,
               SUM(COALESCE(s.output_tokens, 0)) AS output_tokens,
               SUM(COALESCE(t.cost, 0)) AS cost
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND (t.started_at IS NULL OR t.started_at >= ?)
        GROUP BY s.agent_id, t.actor_id
        ORDER BY cost DESC
        """,
        (workspace_id, since),
    ).fetchall()
    agents = [
        AgentAggregate(
            agent_id=row["agent_id"],
            actor_id=row["actor_id"],
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
        WHERE sl.link_type = 'handoff' AND t.workspace_id = ? AND t.started_at >= ?
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
    series: list[dict[str, Any]] = []
    for trace in traces:
        fp = FingerprintRepo.get(conn, trace.trace_id)
        if fp is None:
            continue
        series.append(
            {
                "trace_id": trace.trace_id,
                "ts": trace.started_at,
                "vector": fp.vector,
                "project": trace.project,
                "model": trace.model,
            }
        )
    baselines = FingerprintRepo.list_baselines(conn, limit=20)
    radar = baselines[0].model_dump() if baselines else None
    return BehaviorResponse(
        days=days,
        series=series,
        drift=[],
        radar=radar,
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
        buckets = [0, 0.25, 0.5, 0.75, 1.0]
        for lo, hi in zip(buckets, buckets[1:], strict=False):
            count = sum(1 for s in scores if lo <= s < hi or (hi == 1.0 and s == 1.0))
            histogram.append({"bucket": f"{lo:.2f}-{hi:.2f}", "count": count})
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
        lambda: {"input_tokens": 0, "output_tokens": 0, "cost": 0.0, "traces": 0}
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
        bucket["cost"] = float(bucket["cost"]) + row.cost
        bucket["traces"] = int(bucket["traces"]) + row.traces
    series = [{"key": k, **v} for k, v in sorted(series_map.items())]
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
        SELECT s.waste_category AS category, SUM(s.waste_tokens) AS tokens
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND s.waste_category IS NOT NULL
        GROUP BY s.waste_category
        ORDER BY tokens DESC
        """,
        (workspace_id, since),
    ).fetchall()
    categories = [
        {"category": r["category"], "tokens": int(r["tokens"] or 0)} for r in rows if r["category"]
    ]
    total = sum(c["tokens"] for c in categories)
    return WasteAnalyticsResponse(days=days, categories=categories, total_waste_tokens=total)


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
    insights = [
        InsightRow(
            insight_id=row.insight.insight_id,
            fingerprint=row.insight.fingerprint,
            detector=row.insight.detector,
            severity=row.insight.severity,
            title=row.insight.title,
            body=row.insight.body,
            state=row.state.state,
            savings_estimate=row.insight.savings_estimate,
            action=row.insight.action,
            last_seen_at=row.insight.last_seen_at,
        )
        for row in rows
    ]
    return InsightsResponse(insights=insights, total=len(insights))


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
            verdict=e.verdict,
            lift_pct=e.effect_estimate,
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
    hits: list[SearchHit] = []
    if not q.strip():
        return SearchResponse(q=q, hits=[], total=0)

    title_rows = conn.execute(
        """
        SELECT trace_id, title FROM traces
        WHERE workspace_id = ? AND title LIKE ?
        ORDER BY started_at DESC
        LIMIT ?
        """,
        (workspace_id, f"%{q}%", limit),
    ).fetchall()
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

    if FTS_AVAILABLE and len(hits) < limit:
        try:
            fts_rows = conn.execute(
                """
                SELECT s.trace_id, s.span_id, s.text_inline
                FROM spans_fts f
                JOIN spans s ON s.span_id = f.span_id
                JOIN traces t ON t.trace_id = s.trace_id
                WHERE spans_fts MATCH ? AND t.workspace_id = ?
                LIMIT ?
                """,
                (q, workspace_id, limit - len(hits)),
            ).fetchall()
            for row in fts_rows:
                hits.append(
                    SearchHit(
                        trace_id=str(row["trace_id"]),
                        span_id=str(row["span_id"]),
                        title=None,
                        snippet=str(row["text_inline"] or "")[:200],
                        kind="span",
                    )
                )
        except sqlite3.OperationalError:
            pass

    return SearchResponse(q=q, hits=hits[:limit], total=len(hits[:limit]))


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
            "fts_available": FTS_AVAILABLE,
        },
        gauge=gauge,
    )
