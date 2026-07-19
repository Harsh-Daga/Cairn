"""Build agent, behavior, quality, usage, region, waste, and tail analytics payloads."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

from server.analyze.fingerprint import FINGERPRINT_AXIS_LABELS
from server.analyze.fingerprint_math import (
    MIN_JOINT_BASELINE,
    detect_drift,
    detect_gradual_drift,
)
from server.api.payload_domains.common import append_truncation as _append_truncation
from server.api.payload_domains.common import bounds as _bounds
from server.api.payload_domains.common import data_notes as _data_notes
from server.api.payload_domains.common import day_key as _day_key
from server.api.payload_domains.common import resolved_range as _resolved
from server.api.payload_domains.overview import build_overview
from server.api.schemas import (
    AgentAggregate,
    AgentParseCoverage,
    AgentsLedgerSummary,
    AgentsResponse,
    AgentTrendPoint,
    BaselineProgress,
    BehaviorLedgerSummary,
    BehaviorRadar,
    BehaviorResponse,
    BehaviorSeriesPoint,
    CacheTrendPoint,
    ContextAgentAggregate,
    ContextCoverage,
    ContextEvidence,
    ContextLedgerSummary,
    CostPerSuccessPoint,
    DriftEvent,
    HandoffRow,
    QualityCalibration,
    QualityComponentSummary,
    QualityHistogramBucket,
    QualityInvestigation,
    QualityLedgerSummary,
    QualityOutcome,
    QualityResponse,
    QualityTrendPoint,
    RebilledBlock,
    RegionAggregate,
    RegionsAnalyticsResponse,
    RegionTrendPoint,
    TailAnalyticsResponse,
    UsageAnalyticsResponse,
    UsageSeriesPoint,
    WasteAnalyticsResponse,
    WasteCategory,
)
from server.models.fingerprint import Fingerprint
from server.models.time_range import ResolvedTimeRange
from server.store.pagination import (
    ANALYTICS_LINK_CAP,
    ANALYTICS_SPAN_CAP,
    ANALYTICS_TRACE_CAP,
    fetch_capped,
    truncation_limitation,
)
from server.store.repos.fingerprints import FingerprintRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.traces import TraceListFilters, TraceRepo


def build_agents(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> AgentsResponse:
    since, end, days = _bounds(days, time_range)
    zone = ZoneInfo(time_range.timezone if time_range is not None else "UTC")
    rows, agent_row_total = fetch_capped(
        conn,
        """
        WITH agent_trace AS (
          SELECT s.trace_id, s.agent_id, t.actor_id, a.display_name AS actor_name, t.cost,
                 t.waste_tokens, t.status, t.model, t.source, t.started_at,
                 o.quality_score,
                 SUM(COALESCE(s.input_tokens, 0)) AS input_tokens,
                 SUM(COALESCE(s.output_tokens, 0)) AS output_tokens,
                 SUM(COALESCE(s.input_tokens, 0) + COALESCE(s.output_tokens, 0)) AS agent_tokens
          FROM spans s
          JOIN traces t ON t.trace_id = s.trace_id
          LEFT JOIN actors a ON a.actor_id = t.actor_id
          LEFT JOIN outcomes o ON o.trace_id = t.trace_id
          WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          GROUP BY s.trace_id, s.agent_id, t.actor_id, a.display_name, t.cost,
                   t.waste_tokens, t.status, t.model, t.source, t.started_at, o.quality_score
        ), attributed AS (
          SELECT *, SUM(agent_tokens) OVER (PARTITION BY trace_id) AS trace_span_tokens,
                    COUNT(*) OVER (PARTITION BY trace_id) AS trace_agents
          FROM agent_trace
        )
        SELECT agent_id, actor_id, actor_name, trace_id, started_at, status, model, source,
               input_tokens, output_tokens, waste_tokens, quality_score, agent_tokens,
               trace_span_tokens, trace_agents,
               CASE WHEN trace_span_tokens > 0
                    THEN cost * agent_tokens / trace_span_tokens
                    ELSE cost / trace_agents END AS cost,
               CASE WHEN trace_span_tokens > 0
                    THEN waste_tokens * 1.0 * agent_tokens / trace_span_tokens
                    ELSE waste_tokens * 1.0 / trace_agents END AS attributed_waste
        FROM attributed
        ORDER BY started_at
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )

    buckets: dict[tuple[str | None, str | None, str | None], dict[str, Any]] = {}
    multi_agent_traces: set[str] = set()
    agent_counts: dict[str, set[str | None]] = defaultdict(set)
    for row in rows:
        trace_id = str(row["trace_id"])
        agent_id = row["agent_id"]
        agent_counts[trace_id].add(agent_id)
        key = (agent_id, row["actor_id"], row["actor_name"])
        bucket = buckets.setdefault(
            key,
            {
                "traces": set(),
                "input_tokens": 0,
                "output_tokens": 0,
                "cost": 0.0,
                "waste_tokens": 0.0,
                "quality_sum": 0.0,
                "quality_samples": 0,
                "error_sessions": 0,
                "models": set(),
                "sources": set(),
                "vectors": [],
            },
        )
        if trace_id not in bucket["traces"]:
            bucket["traces"].add(trace_id)
            if str(row["status"] or "") == "error":
                bucket["error_sessions"] += 1
            if row["quality_score"] is not None:
                bucket["quality_sum"] += float(row["quality_score"])
                bucket["quality_samples"] += 1
        bucket["input_tokens"] += int(row["input_tokens"] or 0)
        bucket["output_tokens"] += int(row["output_tokens"] or 0)
        bucket["cost"] += float(row["cost"] or 0.0)
        bucket["waste_tokens"] += float(row["attributed_waste"] or 0.0)
        if row["model"]:
            bucket["models"].add(str(row["model"]))
        if row["source"]:
            bucket["sources"].add(str(row["source"]))

    for trace_id, agents_in_trace in agent_counts.items():
        if len(agents_in_trace) > 1:
            multi_agent_traces.add(trace_id)

    # Fingerprint thumbnails: mean vector across traces where the agent appears.
    fp_rows, _fp_total = fetch_capped(
        conn,
        """
        SELECT DISTINCT s.agent_id, t.actor_id, f.vector_json
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        JOIN fingerprints f ON f.trace_id = t.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        ORDER BY t.started_at, s.agent_id
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    fp_map: dict[tuple[str | None, str | None], list[list[float]]] = defaultdict(list)
    for row in fp_rows:
        try:
            vector = [float(value) for value in json.loads(str(row["vector_json"]))]
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if not vector:
            continue
        fp_map[(row["agent_id"], row["actor_id"])].append(vector)

    agents = []
    for (agent_id, actor_id, actor_name), bucket in buckets.items():
        vectors = fp_map.get((agent_id, actor_id), [])
        thumbnail: list[float] | None = None
        if vectors:
            width = max(len(vector) for vector in vectors)
            sums = [0.0] * width
            for vector in vectors:
                for index, value in enumerate(vector):
                    sums[index] += value
            thumbnail = [round(total / len(vectors), 4) for total in sums]
        sample_size = len(bucket["traces"])
        agents.append(
            AgentAggregate(
                agent_id=agent_id,
                actor_id=actor_id,
                actor_name=actor_name,
                traces=sample_size,
                input_tokens=int(bucket["input_tokens"]),
                output_tokens=int(bucket["output_tokens"]),
                cost=float(bucket["cost"]),
                waste_tokens=int(round(float(bucket["waste_tokens"]))),
                quality_mean=(
                    round(float(bucket["quality_sum"]) / int(bucket["quality_samples"]), 2)
                    if int(bucket["quality_samples"]) > 0
                    else None
                ),
                quality_samples=int(bucket["quality_samples"]),
                error_sessions=int(bucket["error_sessions"]),
                models=sorted(bucket["models"]),
                sources=sorted(bucket["sources"]),
                fingerprint_thumbnail=thumbnail,
                fingerprint_samples=len(vectors),
                sample_size=sample_size,
            )
        )
    agents.sort(key=lambda item: (-item.cost, -(item.sample_size), str(item.agent_id or "")))

    trend_traces: dict[tuple[str, str], set[str]] = defaultdict(set)
    trend_cost: dict[tuple[str, str], float] = defaultdict(float)
    trend_waste: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        day = _day_key(row["started_at"], zone)
        if day is None:
            continue
        agent_key = str(row["agent_id"] or "(default)")
        trend_key = (day, agent_key)
        trend_traces[trend_key].add(str(row["trace_id"]))
        trend_waste[trend_key] += int(round(float(row["attributed_waste"] or 0.0)))
        trend_cost[trend_key] += float(row["cost"] or 0.0)
    trend = [
        AgentTrendPoint(
            day=day,
            agent_id=agent_id,
            traces=len(trend_traces[(day, agent_id)]),
            cost=round(trend_cost[(day, agent_id)], 6),
            waste_tokens=trend_waste[(day, agent_id)],
        )
        for day, agent_id in sorted(trend_traces)
    ]

    handoffs, handoff_total = fetch_capped(
        conn,
        """
        SELECT sl.from_span_id, sl.to_span_id, sl.link_type,
               s1.agent_id AS from_agent, s2.agent_id AS to_agent
        FROM span_links sl
        JOIN spans s1 ON s1.span_id = sl.from_span_id
        JOIN spans s2 ON s2.span_id = sl.to_span_id
        JOIN traces t ON t.trace_id = s1.trace_id
        WHERE sl.link_type = 'handoff' AND t.workspace_id = ?
          AND t.started_at >= ? AND t.started_at < ?
        ORDER BY t.started_at, sl.from_span_id, sl.to_span_id
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_LINK_CAP,
    )
    handoff_rows = [HandoffRow.model_validate(dict(r)) for r in handoffs]

    source_sessions = conn.execute(
        """
        SELECT source, COUNT(*) AS sessions
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        GROUP BY source
        ORDER BY sessions DESC, source
        """,
        (workspace_id, since, end),
    ).fetchall()
    parse_rows = {
        str(row["adapter_id"]): row
        for row in conn.execute(
            """
            SELECT adapter_id, attempts, fully_parsed, degraded, skipped
            FROM adapter_parse_health
            WHERE workspace_id = ?
            """,
            (workspace_id,),
        ).fetchall()
    }
    coverage = []
    for row in source_sessions:
        source = str(row["source"])
        parse = parse_rows.get(source)
        attempts = int(parse["attempts"] or 0) if parse is not None else 0
        fully_parsed = int(parse["fully_parsed"] or 0) if parse is not None else 0
        degraded = int(parse["degraded"] or 0) if parse is not None else 0
        skipped = int(parse["skipped"] or 0) if parse is not None else 0
        coverage.append(
            AgentParseCoverage(
                source=source,
                sessions=int(row["sessions"] or 0),
                attempts=attempts,
                fully_parsed=fully_parsed,
                degraded=degraded,
                skipped=skipped,
                parse_success_pct=(
                    round(fully_parsed / attempts * 100, 2) if attempts > 0 else None
                ),
                limitation=(
                    "Parse-health counters are adapter lifetime totals for this workspace, "
                    "not strictly bounded to the selected range."
                ),
            )
        )

    sample_size = len({str(row["trace_id"]) for row in rows})
    ledger = _agents_ledger(
        agents=agents,
        multi_agent_sessions=len(multi_agent_traces),
        handoffs=len(handoff_rows),
        sample_size=sample_size,
    )
    return AgentsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        agents=agents,
        handoff_matrix=handoff_rows,
        trend=trend,
        coverage=coverage,
        limitations=_agents_limitations(
            agent_sampled=len(rows),
            agent_total=agent_row_total,
            handoff_sampled=len(handoffs),
            handoff_total=handoff_total,
        ),
    )


def _agents_limitations(
    *,
    agent_sampled: int,
    agent_total: int,
    handoff_sampled: int,
    handoff_total: int,
) -> list[str]:
    limitations = [
        "Cost is attributed across agents in a session by span token share.",
        "Fingerprint thumbnails are mean vectors over available fingerprint samples.",
        "Parse-health success rates use workspace adapter counters, not range-scoped attempts.",
        "Quality means use recorded outcome scores only; missing scores stay explicit.",
    ]
    _append_truncation(
        limitations, truncation_limitation("Agent attribution rows", agent_sampled, agent_total)
    )
    _append_truncation(
        limitations, truncation_limitation("Handoff links", handoff_sampled, handoff_total)
    )
    return limitations


def _agents_ledger(
    *,
    agents: list[AgentAggregate],
    multi_agent_sessions: int,
    handoffs: int,
    sample_size: int,
) -> AgentsLedgerSummary:
    limitation = (
        "Agent comparisons are descriptive; sample sizes and model mix must be read before ranking."
    )
    if sample_size == 0:
        return AgentsLedgerSummary(
            conclusion="No sessions fall in the selected range, so agent analytics are empty.",
            agent_count=0,
            multi_agent_sessions=0,
            handoffs=0,
            sample_size=0,
            next_action="Widen the selected range or sync local agent logs.",
            next_action_href="/sessions",
            limitation=limitation,
        )
    top = agents[0] if agents else None
    agent_count = len(agents)
    if handoffs > 0 and top is not None:
        conclusion = (
            f"{agent_count} agents across {sample_size} sessions with {handoffs} handoffs; "
            f"{top.agent_id or 'default'} leads attributed spend."
        )
        next_action = "Inspect the handoff table and open the highest-spend agent sessions."
        next_action_href = f"/sessions?agent={top.agent_id or ''}"
    elif multi_agent_sessions > 0 and top is not None:
        conclusion = (
            f"{multi_agent_sessions} multi-agent sessions observed; "
            f"{top.agent_id or 'default'} leads attributed spend at n={top.sample_size}."
        )
        next_action = f"Filter sessions for {top.agent_id or 'default'}."
        next_action_href = f"/sessions?agent={top.agent_id or ''}"
    elif top is not None:
        conclusion = (
            f"Single-agent work dominates this range ({sample_size} sessions). "
            f"{top.agent_id or 'default'} accounts for the attributed spend."
        )
        next_action = "Review model mix and parse coverage below."
        next_action_href = None
    else:
        conclusion = f"{sample_size} sessions have no agent-attributed spans yet."
        next_action = "Review adapter coverage for agent identifiers."
        next_action_href = "/settings"
    return AgentsLedgerSummary(
        conclusion=conclusion,
        agent_count=agent_count,
        multi_agent_sessions=multi_agent_sessions,
        handoffs=handoffs,
        sample_size=sample_size,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=limitation,
    )


def build_behavior(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> BehaviorResponse:
    since, end, days = _bounds(days, time_range)
    traces = TraceRepo.list(
        conn,
        TraceListFilters(workspace_id=workspace_id, start=since, end=end, limit=500),
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
        latest = group[-1]
        result = detect_drift(latest.vector, baseline)
        if result.drift:
            magnitude = (
                float(result.distance) / float(result.threshold)
                if result.distance is not None
                and result.threshold is not None
                and float(result.threshold) > 0
                else None
            )
            drift.append(
                DriftEvent(
                    kind=result.kind,
                    trace_id=latest.trace_id,
                    project=project_name,
                    model=model_name,
                    distance=result.distance,
                    threshold=result.threshold,
                    per_dim_deltas=result.per_dim_deltas,
                    sample_size=len(baseline),
                    drifted_at=latest.ts,
                    magnitude=round(magnitude, 4) if magnitude is not None else None,
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
        raw_axes = gradual.get("axes")
        axis_rows: list[dict[str, Any]] = (
            [axis for axis in raw_axes if isinstance(axis, dict)]
            if isinstance(raw_axes, list)
            else []
        )
        weeks_outside = [
            float(axis.get("weeks_outside") or 0) for axis in axis_rows if "weeks_outside" in axis
        ]
        drift.append(
            DriftEvent.model_validate(
                {
                    "kind": "gradual",
                    **gradual,
                    "sample_size": len(weekly_means),
                    "drifted_at": weekly_means[-1][0] if weekly_means else None,
                    "magnitude": max(weeks_outside) if weeks_outside else None,
                }
            )
        )

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
    primary_axis: str | None = None
    if radar is not None:
        radar["axes"] = [
            {"axis": label, "value": abs(float(value))}
            for label, value in zip(FINGERPRINT_AXIS_LABELS, radar["mean_vector"], strict=False)
        ][:6]
        if radar["axes"]:
            primary_axis = max(radar["axes"], key=lambda axis: float(axis["value"]))["axis"]
    series.sort(key=lambda row: row.ts or "")
    baseline_ready = strongest_baseline >= MIN_JOINT_BASELINE
    baseline_collected = min(strongest_baseline, MIN_JOINT_BASELINE)
    first_drift = next((event for event in drift if event.trace_id), None)
    ledger = _behavior_ledger(
        fingerprint_sessions=len(series),
        drift_events=len(drift),
        baseline_ready=baseline_ready,
        baseline_collected=baseline_collected,
        baseline_required=MIN_JOINT_BASELINE,
        primary_axis=primary_axis,
        first_drift=first_drift,
    )
    limitations = [
        "Joint-shock drift requires a project/model baseline of "
        f"{MIN_JOINT_BASELINE} sessions before “no drift” is claimable.",
        "Gradual EWMA drift can fire earlier and remains descriptive, not causal.",
        "Nearby Guard instruction-file events are listed on /guard when present for the range.",
        "Fingerprint axes summarize tool mix, retries, context growth, duration, and token flow.",
        "Behavior analytics use at most the 500 most recent sessions in range.",
    ]
    return BehaviorResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        series=series,
        drift=drift,
        radar=BehaviorRadar.model_validate(radar) if radar is not None else None,
        baseline_progress=BaselineProgress(
            collected=baseline_collected,
            required=MIN_JOINT_BASELINE,
            ready=baseline_ready,
            note=f"{baseline_collected}/{MIN_JOINT_BASELINE} sessions collected",
        ),
        data_notes=_data_notes(conn, workspace_id=workspace_id, since=since, end=end),
        limitations=limitations,
    )


def _behavior_ledger(
    *,
    fingerprint_sessions: int,
    drift_events: int,
    baseline_ready: bool,
    baseline_collected: int,
    baseline_required: int,
    primary_axis: str | None,
    first_drift: DriftEvent | None,
) -> BehaviorLedgerSummary:
    limitation = (
        "Behavior drift is descriptive association with a local fingerprint baseline; "
        "it does not prove a model, adapter, or instruction change caused the shift."
    )
    if fingerprint_sessions == 0:
        return BehaviorLedgerSummary(
            conclusion="No fingerprinted sessions in this range.",
            fingerprint_sessions=0,
            drift_events=0,
            baseline_ready=False,
            baseline_collected=0,
            baseline_required=baseline_required,
            primary_axis=None,
            next_action="Sync sessions so fingerprints can be computed",
            next_action_href="/sessions",
            limitation=limitation,
        )
    if drift_events > 0 and first_drift is not None and first_drift.trace_id:
        conclusion = (
            f"{drift_events} drift event(s) vs baseline; first evidence session is "
            f"{first_drift.trace_id[:12]}… ({first_drift.kind.replace('_', ' ')})."
        )
        next_action = "Open the first drifted session"
        next_action_href = f"/sessions/{first_drift.trace_id}"
    elif drift_events > 0:
        conclusion = f"{drift_events} drift event(s) recorded against the local baseline."
        next_action = "Review drifted axes and EWMA trend"
        next_action_href = None
    elif baseline_ready:
        conclusion = (
            f"No joint shock in {fingerprint_sessions} fingerprinted sessions with a ready "
            f"baseline (n≥{baseline_required})."
        )
        next_action = "Keep watching EWMA for gradual movement"
        next_action_href = None
    else:
        conclusion = (
            f"Joint-shock baseline still collecting "
            f"({baseline_collected}/{baseline_required}); EWMA trend remains active."
        )
        next_action = "Accumulate matched project/model sessions"
        next_action_href = "/sessions"
    return BehaviorLedgerSummary(
        conclusion=conclusion,
        fingerprint_sessions=fingerprint_sessions,
        drift_events=drift_events,
        baseline_ready=baseline_ready,
        baseline_collected=baseline_collected,
        baseline_required=baseline_required,
        primary_axis=primary_axis,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=limitation,
    )


def build_quality(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> QualityResponse:
    since, end, days = _bounds(days, time_range)
    zone = ZoneInfo(time_range.timezone if time_range is not None else "UTC")
    traces = TraceRepo.list(
        conn,
        TraceListFilters(workspace_id=workspace_id, start=since, end=end, limit=500),
    )
    outcomes: list[dict[str, Any]] = []
    scores: list[float] = []
    cps: list[dict[str, Any]] = []
    trend_map: dict[str, dict[str, Any]] = {}
    component_sums: dict[str, float] = defaultdict(float)
    component_weight_sums: dict[str, float] = defaultdict(float)
    component_samples: dict[str, int] = defaultdict(int)
    investigations: list[QualityInvestigation] = []
    verified_count = 0
    debt_count = 0
    human_labeled = 0
    human_agreements = 0

    for trace in traces:
        outcome = OutcomeRepo.get(conn, trace.trace_id)
        if outcome is None:
            continue
        started = datetime.fromisoformat(str(trace.started_at))
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        day = started.astimezone(zone).date().isoformat()
        state = _quality_verification_state(outcome)
        row = outcome.model_dump()
        row["trace_id"] = trace.trace_id
        row["cost"] = trace.cost
        row["verification_state"] = state
        row["day"] = day
        outcomes.append(row)

        day_bucket = trend_map.setdefault(
            day,
            {
                "quality_sum": 0.0,
                "quality_samples": 0,
                "verified": 0,
                "debt": 0,
                "sessions": 0,
                "human_up": 0,
                "human_down": 0,
                "cps_sum": 0.0,
                "cps_n": 0,
            },
        )
        day_bucket["sessions"] += 1
        if state == "verified":
            verified_count += 1
            day_bucket["verified"] += 1
        elif state == "debt":
            debt_count += 1
            day_bucket["debt"] += 1

        if outcome.quality_score is not None:
            scores.append(float(outcome.quality_score))
            day_bucket["quality_sum"] += float(outcome.quality_score)
            day_bucket["quality_samples"] += 1
        if outcome.cost_per_success is not None:
            cps.append(
                {
                    "trace_id": trace.trace_id,
                    "day": day,
                    "cost_per_success": outcome.cost_per_success,
                }
            )
            day_bucket["cps_sum"] += float(outcome.cost_per_success)
            day_bucket["cps_n"] += 1
        if outcome.human_label == "up":
            day_bucket["human_up"] += 1
            human_labeled += 1
            if outcome.quality_score is not None and float(outcome.quality_score) >= 50.0:
                human_agreements += 1
        elif outcome.human_label == "down":
            day_bucket["human_down"] += 1
            human_labeled += 1
            if outcome.quality_score is not None and float(outcome.quality_score) < 50.0:
                human_agreements += 1

        components = outcome.quality_components or {}
        weights = outcome.quality_weights or {}
        for name, value in components.items():
            component_sums[name] += float(value)
            component_weight_sums[name] += float(weights.get(name, 0.0))
            component_samples[name] += 1

        investigation = _quality_investigation(outcome)
        if investigation is not None:
            investigations.append(investigation)

    histogram: list[dict[str, Any]] = []
    if scores:
        buckets = [0, 25, 50, 75, 100]
        for lo, hi in zip(buckets, buckets[1:], strict=False):
            count = sum(1 for score in scores if lo <= score < hi or (hi == 100 and score == 100))
            histogram.append({"bucket": f"{lo}-{hi}", "count": count})

    trend = [
        QualityTrendPoint(
            day=day,
            quality_mean=(
                round(float(values["quality_sum"]) / int(values["quality_samples"]), 2)
                if int(values["quality_samples"]) > 0
                else None
            ),
            quality_samples=int(values["quality_samples"]),
            verified_rate=(
                round(int(values["verified"]) / int(values["sessions"]), 4)
                if int(values["sessions"]) > 0
                else None
            ),
            debt_rate=(
                round(int(values["debt"]) / int(values["sessions"]), 4)
                if int(values["sessions"]) > 0
                else None
            ),
            human_up=int(values["human_up"]),
            human_down=int(values["human_down"]),
            mean_cost_per_success=(
                round(float(values["cps_sum"]) / int(values["cps_n"]), 4)
                if int(values["cps_n"]) > 0
                else None
            ),
        )
        for day, values in sorted(trend_map.items())
    ]
    component_summaries = [
        QualityComponentSummary(
            name=name,
            mean=round(component_sums[name] / component_samples[name], 4),
            weight=round(component_weight_sums[name] / component_samples[name], 4),
            samples=component_samples[name],
        )
        for name in sorted(component_samples)
    ]
    outcome_sessions = len(outcomes)
    scored_sessions = len(scores)
    quality_mean = round(sum(scores) / scored_sessions, 2) if scored_sessions else None
    verified_rate = round(verified_count / outcome_sessions, 4) if outcome_sessions else None
    debt_rate = round(debt_count / outcome_sessions, 4) if outcome_sessions else None
    mean_cps = (
        round(sum(float(item["cost_per_success"]) for item in cps) / len(cps), 4) if cps else None
    )
    lucky = sum(1 for item in investigations if item.kind == "lucky_pass")
    unlucky = sum(1 for item in investigations if item.kind == "unlucky_fail")
    coverage_pct = round(100.0 * scored_sessions / outcome_sessions, 2) if outcome_sessions else 0.0
    calibration = QualityCalibration(
        scored_sessions=scored_sessions,
        outcome_sessions=outcome_sessions,
        coverage_pct=coverage_pct,
        human_labeled=human_labeled,
        human_agreements=human_agreements,
        human_agreement_rate=(
            round(human_agreements / human_labeled, 4) if human_labeled else None
        ),
        limitation=(
            "Agreement compares human up/down with process-quality ≥50 classification; "
            "it is not task-outcome ground truth."
        ),
    )
    ledger = _quality_ledger(
        outcome_sessions=outcome_sessions,
        scored_sessions=scored_sessions,
        quality_mean=quality_mean,
        verified_rate=verified_rate,
        debt_rate=debt_rate,
        mean_cps=mean_cps,
        lucky_pass_count=lucky,
        unlucky_fail_count=unlucky,
        first_investigation=investigations[0] if investigations else None,
    )
    limitations = [
        "Process-quality scores are weighted component scores, not task-outcome labels.",
        "Verified completion requires recorded tests or a passing build status.",
        "Verification debt is success-labeled outcomes without test/build evidence.",
        "Unsupported-claim rate stays unavailable until verification receipts land.",
        "Lucky-pass / unlucky-fail flags are descriptive heuristics, not causal findings.",
        "Quality analytics use at most the 500 most recent sessions in range.",
        calibration.limitation,
    ]
    return QualityResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        outcomes=[QualityOutcome.model_validate(item) for item in outcomes],
        histogram=[QualityHistogramBucket.model_validate(item) for item in histogram],
        cost_per_success=[CostPerSuccessPoint.model_validate(item) for item in cps],
        trend=trend,
        components=component_summaries,
        investigations=investigations[:25],
        calibration=calibration,
        data_notes=_data_notes(conn, workspace_id=workspace_id, since=since, end=end),
        limitations=limitations,
    )


def _quality_verification_state(outcome: Any) -> str:
    if int(outcome.tests_failed or 0) > 0 or str(outcome.build_status or "").lower() in {
        "fail",
        "failed",
        "error",
    }:
        return "failed"
    if int(outcome.tests_run or 0) > 0 or str(outcome.build_status or "").lower() in {
        "pass",
        "passed",
        "success",
    }:
        return "verified"
    if str(outcome.outcome_label or "").lower() in {"pass", "passed", "success", "landed"}:
        return "debt"
    if outcome.outcome_label is None and outcome.quality_score is None:
        return "unknown"
    return "unverified"


def _quality_investigation(outcome: Any) -> QualityInvestigation | None:
    score = float(outcome.quality_score) if outcome.quality_score is not None else None
    brittle = bool(outcome.reverted_within_window or outcome.fixup_within_window)
    human = outcome.human_label
    successish = str(outcome.outcome_label or "").lower() in {
        "pass",
        "passed",
        "success",
        "landed",
    } or bool(outcome.commit_landed)

    if score is not None and score >= 70.0 and (brittle or human == "down"):
        reason = (
            "High process-quality with human-down label."
            if human == "down"
            else "High process-quality with same-window revert/fixup."
        )
        return QualityInvestigation(
            kind="lucky_pass",
            trace_id=str(outcome.trace_id),
            quality_score=score,
            outcome_label=outcome.outcome_label,
            human_label=human,
            reason=reason,
            limitation="Heuristic only; does not prove the tests were insufficient.",
        )
    if score is not None and score < 50.0 and (human == "up" or (successish and not brittle)):
        reason = (
            "Low process-quality with human-up label."
            if human == "up"
            else "Low process-quality despite success-like outcome signals."
        )
        return QualityInvestigation(
            kind="unlucky_fail",
            trace_id=str(outcome.trace_id),
            quality_score=score,
            outcome_label=outcome.outcome_label,
            human_label=human,
            reason=reason,
            limitation="Heuristic only; process score and task outcome can diverge honestly.",
        )
    return None


def _quality_ledger(
    *,
    outcome_sessions: int,
    scored_sessions: int,
    quality_mean: float | None,
    verified_rate: float | None,
    debt_rate: float | None,
    mean_cps: float | None,
    lucky_pass_count: int,
    unlucky_fail_count: int,
    first_investigation: QualityInvestigation | None,
) -> QualityLedgerSummary:
    limitation = (
        "Process-quality score is not task outcome. Verified completion and verification debt "
        "use recorded tests/build evidence; unsupported claims are not counted yet."
    )
    if outcome_sessions == 0:
        return QualityLedgerSummary(
            conclusion="No outcomes captured in this range.",
            outcome_sessions=0,
            scored_sessions=0,
            quality_mean=None,
            verified_completion_rate=None,
            verification_debt_rate=None,
            unsupported_claim_rate=None,
            mean_cost_per_success=None,
            lucky_pass_count=0,
            unlucky_fail_count=0,
            next_action="Enable outcome capture in Settings",
            next_action_href="/settings",
            limitation=limitation,
        )

    score_text = f"{quality_mean:.1f}" if quality_mean is not None else "unscored"
    verified_text = (
        f"{verified_rate * 100:.0f}% verified" if verified_rate is not None else "verification n/a"
    )
    debt_text = f"{debt_rate * 100:.0f}% verification debt" if debt_rate is not None else "debt n/a"
    conclusion = (
        f"{scored_sessions}/{outcome_sessions} scored · mean process quality {score_text} · "
        f"{verified_text} · {debt_text}."
    )
    if lucky_pass_count or unlucky_fail_count:
        conclusion += (
            f" {lucky_pass_count} lucky-pass and {unlucky_fail_count} unlucky-fail "
            "investigation(s) flagged."
        )

    if first_investigation is not None:
        next_action = f"Inspect {first_investigation.kind.replace('_', ' ')} session"
        next_action_href = f"/sessions/{first_investigation.trace_id}"
    elif debt_rate is not None and debt_rate >= 0.2:
        next_action = "Review verification-debt sessions"
        next_action_href = "/sessions?q=verification:debt"
    else:
        next_action = "Label a few sessions to calibrate agreement"
        next_action_href = "/sessions"

    return QualityLedgerSummary(
        conclusion=conclusion,
        outcome_sessions=outcome_sessions,
        scored_sessions=scored_sessions,
        quality_mean=quality_mean,
        verified_completion_rate=verified_rate,
        verification_debt_rate=debt_rate,
        unsupported_claim_rate=None,
        mean_cost_per_success=mean_cps,
        lucky_pass_count=lucky_pass_count,
        unlucky_fail_count=unlucky_fail_count,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=limitation,
    )


def build_usage_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    group_by: str = "day",
    time_range: ResolvedTimeRange | None = None,
) -> UsageAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    rows, _usage_total = fetch_capped(
        conn,
        """
        SELECT started_at, model, source, project, input_tokens, output_tokens,
               waste_tokens, cost
        FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        ORDER BY started_at ASC
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    zone = ZoneInfo(time_range.timezone if time_range is not None else "UTC")
    series_map: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "output_tokens": 0,
            "waste_tokens": 0,
            "cost": 0.0,
            "traces": 0,
        }
    )
    for row in rows:
        if group_by == "day":
            key = _day_key(row["started_at"], zone)
            if key is None:
                continue
        elif group_by == "model":
            key = str(row["model"] or "(unknown)")
        elif group_by == "source":
            key = str(row["source"])
        elif group_by == "project":
            key = str(row["project"] or "(unknown)")
        else:
            key = _day_key(row["started_at"], zone)
            if key is None:
                continue
        bucket = series_map[key]
        bucket["input_tokens"] = int(bucket["input_tokens"]) + int(row["input_tokens"] or 0)
        bucket["output_tokens"] = int(bucket["output_tokens"]) + int(row["output_tokens"] or 0)
        bucket["waste_tokens"] = int(bucket["waste_tokens"]) + int(row["waste_tokens"] or 0)
        bucket["cost"] = float(bucket["cost"]) + float(row["cost"] or 0.0)
        bucket["traces"] = int(bucket["traces"]) + 1
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
    return UsageAnalyticsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        group_by=group_by,
        series=series,
    )


def build_regions_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> RegionsAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    zone = ZoneInfo(time_range.timezone if time_range is not None else "UTC")
    rows = conn.execute(
        """
        SELECT cr.region, SUM(cr.tokens) AS tokens, SUM(cr.cost) AS cost, COUNT(*) AS spans
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        GROUP BY cr.region
        ORDER BY tokens DESC
        """,
        (workspace_id, since, end),
    ).fetchall()
    trend_rows, _trend_total = fetch_capped(
        conn,
        """
        SELECT t.started_at, cr.region, cr.tokens, cr.cost
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        ORDER BY t.started_at, cr.region
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_SPAN_CAP,
    )
    trend_map: dict[tuple[str, str], tuple[int, float]] = {}
    for row in trend_rows:
        day = _day_key(row["started_at"], zone)
        if day is None:
            continue
        key = (day, str(row["region"]))
        tokens, cost = trend_map.get(key, (0, 0.0))
        trend_map[key] = (
            tokens + int(row["tokens"] or 0),
            cost + float(row["cost"] or 0.0),
        )

    rebill_rows = conn.execute(
        """
        SELECT cr.content_hash, cr.region, COUNT(*) AS occurrences,
               COUNT(DISTINCT s.trace_id) AS sessions,
               SUM(cr.tokens) AS tokens, MAX(cr.tokens) AS largest_single_tokens,
               SUM(cr.cost) AS cost, MIN(s.trace_id) AS trace_id, MIN(s.span_id) AS span_id
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND cr.content_hash IS NOT NULL AND cr.content_hash != ''
        GROUP BY cr.content_hash, cr.region
        HAVING COUNT(*) > 1
        ORDER BY (SUM(cr.tokens) - MAX(cr.tokens)) DESC, COUNT(*) DESC
        LIMIT 20
        """,
        (workspace_id, since, end),
    ).fetchall()
    fix_by_region = {
        "system": "Shorten stable system instructions or move optional guidance behind retrieval.",
        "tool_schema": "Load only tool schemas needed for the current step.",
        "tool_result": "Summarize or reference large tool results after extracting needed facts.",
        "retrieved": "Deduplicate retrieval and reduce overlapping chunks.",
        "user": "Preserve user intent; do not remove it solely to reduce context.",
        "history": "Compact resolved history while retaining decisions and verification evidence.",
    }
    rebilled_blocks = [
        RebilledBlock(
            block_id=f"block-{str(row['content_hash'])[:12]}",
            region=str(row["region"]),
            occurrences=int(row["occurrences"] or 0),
            sessions=int(row["sessions"] or 0),
            tokens=int(row["tokens"] or 0),
            estimated_rebilled_tokens=max(
                0,
                int(row["tokens"] or 0) - int(row["largest_single_tokens"] or 0),
            ),
            cost=float(row["cost"] or 0.0),
            suggested_fix=fix_by_region.get(
                str(row["region"]),
                "Inspect the repeated block before changing retention.",
            ),
            evidence=ContextEvidence(
                trace_id=str(row["trace_id"]),
                span_id=str(row["span_id"]),
                region=str(row["region"]),
                label="Open one recorded occurrence",
            ),
            limitation=(
                "Re-billed tokens are estimated as repeated same-hash tokens after one retained "
                "copy; provider cache billing and actual avoidability are not inferred."
            ),
        )
        for row in rebill_rows
    ]

    cache_rows, _cache_total = fetch_capped(
        conn,
        """
        SELECT t.trace_id, t.started_at, t.input_tokens, t.cache_read_tokens,
               t.cache_creation_tokens,
               EXISTS(
                 SELECT 1 FROM spans s
                 WHERE s.trace_id = t.trace_id
                   AND (s.cache_read_tokens IS NOT NULL OR s.cache_creation_tokens IS NOT NULL)
               ) AS cache_measured
        FROM traces t
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        ORDER BY t.started_at
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    cache_map: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "input_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "measured_sessions": 0,
            "total_sessions": 0,
        }
    )
    for row in cache_rows:
        started_at = datetime.fromisoformat(str(row["started_at"]))
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        day = started_at.astimezone(zone).date().isoformat()
        bucket = cache_map[day]
        bucket["input_tokens"] += int(row["input_tokens"] or 0)
        bucket["cache_read_tokens"] += int(row["cache_read_tokens"] or 0)
        bucket["cache_creation_tokens"] += int(row["cache_creation_tokens"] or 0)
        bucket["measured_sessions"] += int(row["cache_measured"] or 0)
        bucket["total_sessions"] += 1
    cache_trend: list[CacheTrendPoint] = []
    for day, values in sorted(cache_map.items()):
        measured = values["measured_sessions"]
        denominator = values["input_tokens"] + values["cache_read_tokens"]
        hit_ratio = (
            values["cache_read_tokens"] / denominator if measured > 0 and denominator > 0 else None
        )
        cache_trend.append(
            CacheTrendPoint(
                day=day,
                input_tokens=values["input_tokens"],
                cache_read_tokens=values["cache_read_tokens"],
                cache_creation_tokens=values["cache_creation_tokens"],
                measured_sessions=measured,
                total_sessions=values["total_sessions"],
                hit_ratio=hit_ratio,
                estimated_savings_usd=None,
                limitation=(
                    "No savings value is estimated: provider cache pricing, eligibility, and "
                    "counter semantics are not established by these normalized fields."
                ),
            )
        )

    agent_rows = conn.execute(
        """
        SELECT COALESCE(s.agent_id, t.actor_id, '(unknown)') AS agent_id,
               cr.region, COUNT(*) AS spans, COUNT(DISTINCT s.trace_id) AS sessions,
               SUM(cr.tokens) AS tokens, SUM(cr.cost) AS cost
        FROM context_regions cr
        JOIN spans s ON s.span_id = cr.span_id
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        GROUP BY COALESCE(s.agent_id, t.actor_id, '(unknown)'), cr.region
        ORDER BY agent_id, tokens DESC
        """,
        (workspace_id, since, end),
    ).fetchall()
    agent_session_rows = conn.execute(
        """
        SELECT COALESCE(s.agent_id, t.actor_id, '(unknown)') AS agent_id,
               COUNT(DISTINCT s.trace_id) AS sessions
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND EXISTS(SELECT 1 FROM context_regions cr WHERE cr.span_id = s.span_id)
        GROUP BY COALESCE(s.agent_id, t.actor_id, '(unknown)')
        """,
        (workspace_id, since, end),
    ).fetchall()
    agent_sessions = {str(row["agent_id"]): int(row["sessions"] or 0) for row in agent_session_rows}
    agent_map: dict[str, dict[str, Any]] = {}
    for row in agent_rows:
        agent_id = str(row["agent_id"])
        item = agent_map.setdefault(
            agent_id,
            {"spans": 0, "tokens": 0, "cost": 0.0, "regions": []},
        )
        item["spans"] += int(row["spans"] or 0)
        item["tokens"] += int(row["tokens"] or 0)
        item["cost"] += float(row["cost"] or 0.0)
        item["regions"].append((str(row["region"]), int(row["tokens"] or 0)))
    agents = [
        ContextAgentAggregate(
            agent_id=agent_id,
            sessions=agent_sessions.get(agent_id, 0),
            spans=int(values["spans"]),
            tokens=int(values["tokens"]),
            cost=float(values["cost"]),
            top_region=max(values["regions"], key=lambda value: value[1])[0]
            if values["regions"]
            else None,
        )
        for agent_id, values in sorted(
            agent_map.items(), key=lambda item: int(item[1]["tokens"]), reverse=True
        )
    ]

    coverage_rows = conn.execute(
        """
        SELECT t.source, COUNT(*) AS sessions,
               SUM(EXISTS(
                 SELECT 1 FROM spans s JOIN context_regions cr ON cr.span_id = s.span_id
                 WHERE s.trace_id = t.trace_id
               )) AS region_sessions,
               SUM(EXISTS(
                 SELECT 1 FROM spans s
                 WHERE s.trace_id = t.trace_id
                   AND (s.cache_read_tokens IS NOT NULL OR s.cache_creation_tokens IS NOT NULL)
               )) AS cache_measured_sessions,
               SUM(t.started_at IS NOT NULL AND t.ended_at IS NOT NULL) AS timestamp_sessions,
               SUM(COALESCE(dq.dropped_events, 0)) AS dropped_events
        FROM traces t
        LEFT JOIN data_quality dq ON dq.trace_id = t.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
        GROUP BY t.source
        ORDER BY sessions DESC, t.source
        """,
        (workspace_id, since, end),
    ).fetchall()
    coverage = [
        ContextCoverage(
            source=str(row["source"]),
            sessions=int(row["sessions"] or 0),
            region_sessions=int(row["region_sessions"] or 0),
            region_coverage_pct=(
                int(row["region_sessions"] or 0) / max(1, int(row["sessions"] or 0)) * 100
            ),
            cache_measured_sessions=int(row["cache_measured_sessions"] or 0),
            cache_coverage_pct=(
                int(row["cache_measured_sessions"] or 0) / max(1, int(row["sessions"] or 0)) * 100
            ),
            timestamp_sessions=int(row["timestamp_sessions"] or 0),
            dropped_events=int(row["dropped_events"] or 0),
            limitation=(
                "Coverage reports field presence, not semantic correctness or provider support."
            ),
        )
        for row in coverage_rows
    ]
    region_aggregates = [
        RegionAggregate(
            region=str(row["region"]),
            tokens=int(row["tokens"] or 0),
            spans=int(row["spans"] or 0),
            cost=float(row["cost"] or 0.0),
        )
        for row in rows
    ]
    schema_region = next(
        (region for region in region_aggregates if region.region == "tool_schema"),
        None,
    )
    schema_overhead_tokens = schema_region.tokens if schema_region is not None else 0
    schema_overhead_cost = schema_region.cost if schema_region is not None else 0.0
    mapped_region_tokens = sum(region.tokens for region in region_aggregates)
    mapped_region_cost = sum(region.cost for region in region_aggregates)
    estimated_rebilled_tokens = sum(block.estimated_rebilled_tokens for block in rebilled_blocks)
    tool_result_tokens = next(
        (region.tokens for region in region_aggregates if region.region == "tool_result"),
        0,
    )
    tool_result_share = (
        (tool_result_tokens / mapped_region_tokens) * 100 if mapped_region_tokens > 0 else 0.0
    )
    repetition_intensity = (
        estimated_rebilled_tokens / mapped_region_tokens if mapped_region_tokens > 0 else None
    )
    primary_region = region_aggregates[0].region if region_aggregates else None
    sessions_total = sum(row.sessions for row in coverage)
    sessions_with_regions = sum(row.region_sessions for row in coverage)
    region_coverage_pct = (
        sessions_with_regions / sessions_total * 100 if sessions_total > 0 else 0.0
    )
    ledger = _context_ledger(
        mapped_region_tokens=mapped_region_tokens,
        mapped_region_cost=mapped_region_cost,
        estimated_rebilled_tokens=estimated_rebilled_tokens,
        schema_overhead_tokens=schema_overhead_tokens,
        tool_result_share=tool_result_share,
        repetition_intensity=repetition_intensity,
        primary_region=primary_region,
        sessions_with_regions=sessions_with_regions,
        sessions_total=sessions_total,
        region_coverage_pct=region_coverage_pct,
        rebilled_blocks=rebilled_blocks,
    )
    return RegionsAnalyticsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        ledger=ledger,
        regions=region_aggregates,
        trend=[
            RegionTrendPoint(day=day, region=region, tokens=values[0], cost=values[1])
            for (day, region), values in sorted(trend_map.items())
        ],
        rebilled_blocks=rebilled_blocks,
        cache_trend=cache_trend,
        agents=agents,
        coverage=coverage,
        schema_overhead_tokens=schema_overhead_tokens,
        schema_overhead_cost=schema_overhead_cost,
        limitations=[
            "Context-region availability and classification vary by adapter and retention mode.",
            "Repeated same-hash blocks are evidence of repetition, not proof they were avoidable.",
            (
                "Cache savings remain unavailable without provider-specific measured "
                "billing semantics."
            ),
            "Region cost may be measured or estimated by the source; inspect adapter coverage.",
            "Mapped region tokens accumulate across turns and are not a partition of input tokens.",
        ],
    )


def _context_ledger(
    *,
    mapped_region_tokens: int,
    mapped_region_cost: float,
    estimated_rebilled_tokens: int,
    schema_overhead_tokens: int,
    tool_result_share: float,
    repetition_intensity: float | None,
    primary_region: str | None,
    sessions_with_regions: int,
    sessions_total: int,
    region_coverage_pct: float,
    rebilled_blocks: list[RebilledBlock],
) -> ContextLedgerSummary:
    """Build a deterministic answer-first Context conclusion."""
    region_labels = {
        "system": "system prompt",
        "tool_schema": "tool schemas",
        "tool_result": "tool results",
        "retrieved": "retrieved context",
        "user": "user messages",
        "history": "conversation history",
        "assistant_history": "conversation history",
    }
    limitation = (
        "Ledger ratios use mapped region rows only; they do not prove avoidable spend or "
        "provider cache savings."
    )
    if sessions_total == 0:
        return ContextLedgerSummary(
            conclusion="No sessions fall in the selected range, so context composition is empty.",
            mapped_region_tokens=0,
            mapped_region_cost=0.0,
            estimated_rebilled_tokens=0,
            schema_overhead_tokens=0,
            tool_result_share=0.0,
            repetition_intensity=None,
            primary_region=None,
            sessions_with_regions=0,
            sessions_total=0,
            region_coverage_pct=0.0,
            cache_savings_available=False,
            next_action="Widen the selected range or sync local agent logs.",
            next_action_href="/sessions",
            limitation=limitation,
        )
    if mapped_region_tokens <= 0:
        return ContextLedgerSummary(
            conclusion=(
                f"Only {region_coverage_pct:.0f}% of {sessions_total} sessions have mapped "
                "context regions; composition cannot be answered yet."
            ),
            mapped_region_tokens=0,
            mapped_region_cost=0.0,
            estimated_rebilled_tokens=0,
            schema_overhead_tokens=schema_overhead_tokens,
            tool_result_share=0.0,
            repetition_intensity=None,
            primary_region=None,
            sessions_with_regions=sessions_with_regions,
            sessions_total=sessions_total,
            region_coverage_pct=region_coverage_pct,
            cache_savings_available=False,
            next_action="Review adapter coverage and parse health before trusting region charts.",
            next_action_href="/settings",
            limitation=limitation,
        )

    primary_label = region_labels.get(primary_region or "", primary_region or "unknown")
    intensity = repetition_intensity or 0.0
    if intensity >= 0.25 and rebilled_blocks:
        top = rebilled_blocks[0]
        conclusion = (
            f"{primary_label.capitalize()} dominate mapped tokens, and about "
            f"{intensity * 100:.0f}% of mapped region tokens look like same-hash repetition."
        )
        region_label = region_labels.get(top.region, top.region)
        next_action = f"Inspect the top re-billed {region_label} block."
        next_action_href = f"/sessions/{top.evidence.trace_id}?span={top.evidence.span_id}"
    elif tool_result_share >= 40.0:
        conclusion = (
            f"Tool results are {tool_result_share:.0f}% of mapped region tokens; "
            f"{primary_label} is the largest recorded region."
        )
        next_action = "Open the largest tool-result sessions and collapse retained results."
        next_action_href = "/sessions?q=tool%3A"
    elif schema_overhead_tokens > 0 and schema_overhead_tokens / mapped_region_tokens >= 0.15:
        conclusion = (
            f"Tool-schema overhead is {schema_overhead_tokens} tokens "
            f"({schema_overhead_tokens / mapped_region_tokens * 100:.0f}% of mapped regions)."
        )
        next_action = "Compare agents with high schema share and trim unused tool definitions."
        next_action_href = "/agents"
    else:
        conclusion = (
            f"{primary_label.capitalize()} lead mapped context "
            f"({mapped_region_tokens} tokens across {sessions_with_regions}/"
            f"{sessions_total} sessions with region evidence)."
        )
        next_action = "Review region trend and adapter coverage for uneven mapping."
        next_action_href = None

    return ContextLedgerSummary(
        conclusion=conclusion,
        mapped_region_tokens=mapped_region_tokens,
        mapped_region_cost=mapped_region_cost,
        estimated_rebilled_tokens=estimated_rebilled_tokens,
        schema_overhead_tokens=schema_overhead_tokens,
        tool_result_share=round(tool_result_share, 2),
        repetition_intensity=(round(intensity, 4) if repetition_intensity is not None else None),
        primary_region=primary_region,
        sessions_with_regions=sessions_with_regions,
        sessions_total=sessions_total,
        region_coverage_pct=round(region_coverage_pct, 2),
        cache_savings_available=False,
        next_action=next_action,
        next_action_href=next_action_href,
        limitation=limitation,
    )


def build_waste_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> WasteAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    rows = conn.execute(
        """
        SELECT s.waste_category AS category, SUM(s.waste_tokens) AS tokens, COUNT(*) AS events
        FROM spans s
        JOIN traces t ON t.trace_id = s.trace_id
        WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
          AND s.waste_category IS NOT NULL
        GROUP BY s.waste_category
        ORDER BY tokens DESC
        """,
        (workspace_id, since, end),
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
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ?
        """,
        (workspace_id, since, end),
    ).fetchone()
    trace_total = int(trace_waste_row["tokens"] or 0) if trace_waste_row else 0
    residual = max(0, trace_total - categorized_total)
    if residual:
        residual_row = conn.execute(
            """
            SELECT COUNT(*) AS events
            FROM traces t
            WHERE t.workspace_id = ? AND t.started_at >= ? AND t.started_at < ?
              AND t.waste_tokens > COALESCE((
                SELECT SUM(s.waste_tokens) FROM spans s WHERE s.trace_id = t.trace_id
              ), 0)
            """,
            (workspace_id, since, end),
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
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        categories=categories,
        total_waste_tokens=trace_total,
    )


def build_tail_analytics(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    days: int = 30,
    time_range: ResolvedTimeRange | None = None,
) -> TailAnalyticsResponse:
    since, end, days = _bounds(days, time_range)
    overview = build_overview(conn, workspace_id=workspace_id, days=days, time_range=time_range)
    cost_rows, _cost_total = fetch_capped(
        conn,
        """
        SELECT cost FROM traces
        WHERE workspace_id = ? AND started_at >= ? AND started_at < ? AND cost > 0
        ORDER BY started_at, trace_id
        """,
        (workspace_id, since, end),
        cap=ANALYTICS_TRACE_CAP,
    )
    costs = [float(r["cost"] or 0.0) for r in cost_rows]
    exceedances: list[float] = []
    if len(costs) >= 5:
        arr = np.array(costs, dtype=float)
        threshold = float(np.quantile(arr, 0.9))
        exceedances = [float(x - threshold) for x in arr if x > threshold]
    return TailAnalyticsResponse(
        days=days,
        resolved_range=_resolved(days=days, since=since, end=end, time_range=time_range),
        tail_risk=overview.tail_risk,
        exceedances=exceedances,
    )
