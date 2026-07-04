"""Pydantic response models for §6.2 read API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from server.models.insight import InsightLifecycle, InsightSeverity
from server.models.span import Span
from server.models.trace import Trace


class DataNote(BaseModel):
    source: str
    sessions: int
    issue: str
    message: str
    help_url: str | None = None


class NarrativeSentence(BaseModel):
    text: str
    filter: dict[str, str] | None = None


class TailRisk(BaseModel):
    expected_worst_cost: float | None = None
    exceedance_count: int = 0
    threshold: float | None = None


class OverviewResponse(BaseModel):
    days: int
    kpis: dict[str, float | int | None]
    narrative: list[NarrativeSentence]
    tail_risk: TailRisk
    data_notes: list[DataNote]


class TraceRow(BaseModel):
    trace_id: str
    source: str
    title: str | None
    project: str | None
    actor_id: str | None
    model: str | None
    started_at: str | None
    ended_at: str | None
    status: str
    input_tokens: int
    output_tokens: int
    cost: float
    cost_source: str
    span_count: int
    waste_tokens: int
    difficulty: float | None


class TracesListResponse(BaseModel):
    traces: list[TraceRow]
    total: int
    limit: int
    offset: int


class SpanNode(BaseModel):
    span: Span
    children: list[SpanNode] = Field(default_factory=list)


class SpanLink(BaseModel):
    from_span_id: str
    to_span_id: str
    link_type: str


class TraceDetailResponse(BaseModel):
    trace: Trace
    spans: list[Span]
    tree: list[SpanNode]
    links: list[SpanLink]
    regions: list[dict[str, Any]]
    diagnostics: dict[str, Any] | None
    quality: dict[str, Any] | None


class ReplayResponse(BaseModel):
    trace_id: str
    seq: int
    spans: list[Span]
    summary: dict[str, Any]


class AgentAggregate(BaseModel):
    agent_id: str | None
    actor_id: str | None
    traces: int
    input_tokens: int
    output_tokens: int
    cost: float


class AgentsResponse(BaseModel):
    days: int
    agents: list[AgentAggregate]
    handoff_matrix: list[dict[str, Any]]


class BehaviorResponse(BaseModel):
    days: int
    series: list[dict[str, Any]]
    drift: list[dict[str, Any]]
    radar: dict[str, Any] | None
    data_notes: list[DataNote]


class QualityResponse(BaseModel):
    days: int
    outcomes: list[dict[str, Any]]
    histogram: list[dict[str, Any]]
    cost_per_success: list[dict[str, Any]]
    data_notes: list[DataNote]


class UsageAnalyticsResponse(BaseModel):
    days: int
    group_by: str
    series: list[dict[str, Any]]


class RegionsAnalyticsResponse(BaseModel):
    days: int
    regions: list[dict[str, Any]]


class WasteAnalyticsResponse(BaseModel):
    days: int
    categories: list[dict[str, Any]]
    total_waste_tokens: int


class TailAnalyticsResponse(BaseModel):
    days: int
    tail_risk: TailRisk
    exceedances: list[float]


class InsightRow(BaseModel):
    insight_id: str
    fingerprint: str
    detector: str
    severity: InsightSeverity
    title: str
    body: str
    state: InsightLifecycle
    savings_estimate: float | None
    action: str | None
    last_seen_at: str


class InsightsResponse(BaseModel):
    insights: list[InsightRow]
    total: int


class EvidenceChainResponse(BaseModel):
    insight_id: str
    evidence_id: str
    producer: str
    produced_at: str
    trace_ids: list[str]
    span_ids: list[str] | None
    metrics: dict[str, Any]
    spans: list[Span]


class ExperimentRow(BaseModel):
    experiment_id: str
    status: str
    target_file: str | None
    created_at: str
    verdict: str | None
    lift_pct: float | None


class ExperimentsResponse(BaseModel):
    experiments: list[ExperimentRow]


class ExperimentDetailResponse(BaseModel):
    experiment: dict[str, Any]


class SearchHit(BaseModel):
    trace_id: str
    span_id: str | None
    title: str | None
    snippet: str
    kind: Literal["trace", "span"]


class SearchResponse(BaseModel):
    q: str
    hits: list[SearchHit]
    total: int


class WorkspaceAdapter(BaseModel):
    source: str
    streams: int
    cursor_updated_at: str | None


class WorkspaceResponse(BaseModel):
    workspace_id: str
    root_path: str
    name: str
    adapters: list[WorkspaceAdapter]
    health: dict[str, Any]


class ActionManifestEntry(BaseModel):
    name: str
    title: str
    category: str
    params_schema: dict[str, Any]
    async_job: bool


class ActionsManifestResponse(BaseModel):
    actions: list[ActionManifestEntry]


class ActionResultResponse(BaseModel):
    ok: bool
    result: dict[str, Any] | None = None
    job_id: str | None = None


class ErrorResponse(BaseModel):
    error: dict[str, str]
