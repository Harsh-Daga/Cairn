"""Agent, behavior, quality, usage, region, waste, and tail schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from server.api.schema.overview import DataNote, TailRisk
from server.models.outcome import Outcome
from server.models.time_range import ResolvedTimeRange


class AgentAggregate(BaseModel):
    agent_id: str | None
    actor_id: str | None
    actor_name: str | None
    traces: int
    input_tokens: int
    output_tokens: int
    cost: float
    waste_tokens: int = 0
    quality_mean: float | None = None
    quality_samples: int = 0
    error_sessions: int = 0
    models: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    fingerprint_thumbnail: list[float] | None = None
    fingerprint_samples: int = 0
    sample_size: int = 0


class HandoffRow(BaseModel):
    from_span_id: str
    to_span_id: str
    link_type: str
    from_agent: str | None
    to_agent: str | None


class AgentTrendPoint(BaseModel):
    day: str
    agent_id: str
    traces: int
    cost: float
    waste_tokens: int


class AgentParseCoverage(BaseModel):
    source: str
    sessions: int
    attempts: int
    fully_parsed: int
    degraded: int
    skipped: int
    parse_success_pct: float | None
    limitation: str


class AgentsLedgerSummary(BaseModel):
    conclusion: str
    agent_count: int
    multi_agent_sessions: int
    handoffs: int
    sample_size: int
    next_action: str
    next_action_href: str | None
    limitation: str


class AgentsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: AgentsLedgerSummary
    agents: list[AgentAggregate]
    handoff_matrix: list[HandoffRow]
    trend: list[AgentTrendPoint]
    coverage: list[AgentParseCoverage]
    limitations: list[str]


class BehaviorSeriesPoint(BaseModel):
    trace_id: str
    ts: str | None
    vector: list[float]
    project: str | None
    model: str | None


class DriftEvent(BaseModel):
    kind: str
    trace_id: str | None = None
    project: str | None = None
    model: str | None = None
    distance: float | None = None
    threshold: float | None = None
    per_dim_deltas: list[float] = Field(default_factory=list)
    drift: bool | None = None
    axes: list[DriftAxis] = Field(default_factory=list)
    data_notes: list[str] = Field(default_factory=list)
    sample_size: int = 0
    drifted_at: str | None = None
    magnitude: float | None = None


class DriftAxis(BaseModel):
    axis: int
    axis_label: str
    weeks_outside: int
    ewma: float
    bounds: list[float]


class RadarAxis(BaseModel):
    axis: str
    value: float


class BehaviorRadar(BaseModel):
    project: str
    model: str
    week: str
    mean_vector: list[float]
    cov_inv: list[list[float]]
    n: int
    axes: list[RadarAxis]


class BaselineProgress(BaseModel):
    collected: int
    required: int
    ready: bool
    note: str


class BehaviorLedgerSummary(BaseModel):
    conclusion: str
    fingerprint_sessions: int
    drift_events: int
    baseline_ready: bool
    baseline_collected: int
    baseline_required: int
    primary_axis: str | None
    next_action: str
    next_action_href: str | None
    limitation: str


class BehaviorResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: BehaviorLedgerSummary
    series: list[BehaviorSeriesPoint]
    drift: list[DriftEvent]
    radar: BehaviorRadar | None
    baseline_progress: BaselineProgress
    data_notes: list[DataNote]
    limitations: list[str]


class QualityOutcome(Outcome):
    cost: float
    verification_state: str = "unknown"
    day: str | None = None


class QualityHistogramBucket(BaseModel):
    bucket: str
    count: int


class CostPerSuccessPoint(BaseModel):
    trace_id: str
    day: str
    cost_per_success: float


class QualityTrendPoint(BaseModel):
    day: str
    quality_mean: float | None
    quality_samples: int
    verified_rate: float | None
    debt_rate: float | None
    human_up: int = 0
    human_down: int = 0
    mean_cost_per_success: float | None = None


class QualityComponentSummary(BaseModel):
    name: str
    mean: float
    weight: float
    samples: int


class QualityInvestigation(BaseModel):
    kind: str
    trace_id: str
    quality_score: float | None
    outcome_label: str | None
    human_label: str | None
    reason: str
    limitation: str


class QualityCalibration(BaseModel):
    scored_sessions: int
    outcome_sessions: int
    coverage_pct: float
    human_labeled: int
    human_agreements: int
    human_agreement_rate: float | None
    limitation: str


class QualityLedgerSummary(BaseModel):
    conclusion: str
    outcome_sessions: int
    scored_sessions: int
    quality_mean: float | None
    verified_completion_rate: float | None
    verification_debt_rate: float | None
    unsupported_claim_rate: float | None
    mean_cost_per_success: float | None
    lucky_pass_count: int
    unlucky_fail_count: int
    next_action: str
    next_action_href: str | None
    limitation: str


class QualityResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: QualityLedgerSummary
    outcomes: list[QualityOutcome]
    histogram: list[QualityHistogramBucket]
    cost_per_success: list[CostPerSuccessPoint]
    trend: list[QualityTrendPoint]
    components: list[QualityComponentSummary]
    investigations: list[QualityInvestigation]
    calibration: QualityCalibration
    data_notes: list[DataNote]
    limitations: list[str]


class UsageSeriesPoint(BaseModel):
    key: str
    input_tokens: int
    output_tokens: int
    waste_tokens: int
    cost: float
    traces: int


class UsageAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    group_by: str
    series: list[UsageSeriesPoint]


class RegionAggregate(BaseModel):
    region: str
    tokens: int
    spans: int
    cost: float = 0.0


class RegionTrendPoint(BaseModel):
    day: str
    region: str
    tokens: int
    cost: float


class ContextEvidence(BaseModel):
    trace_id: str
    span_id: str
    region: str
    label: str


class RebilledBlock(BaseModel):
    block_id: str
    region: str
    occurrences: int
    sessions: int
    tokens: int
    estimated_rebilled_tokens: int
    cost: float
    suggested_fix: str
    evidence: ContextEvidence
    limitation: str


class CacheTrendPoint(BaseModel):
    day: str
    input_tokens: int
    cache_read_tokens: int
    cache_creation_tokens: int
    measured_sessions: int
    total_sessions: int
    hit_ratio: float | None
    estimated_savings_usd: float | None
    limitation: str


class ContextAgentAggregate(BaseModel):
    agent_id: str
    sessions: int
    spans: int
    tokens: int
    cost: float
    top_region: str | None


class ContextCoverage(BaseModel):
    source: str
    sessions: int
    region_sessions: int
    region_coverage_pct: float
    cache_measured_sessions: int
    cache_coverage_pct: float
    timestamp_sessions: int
    dropped_events: int
    limitation: str


class ContextLedgerSummary(BaseModel):
    """Answer-first Context conclusion. Descriptive only; never causal."""

    conclusion: str
    mapped_region_tokens: int
    mapped_region_cost: float
    estimated_rebilled_tokens: int
    schema_overhead_tokens: int
    tool_result_share: float
    repetition_intensity: float | None
    primary_region: str | None
    sessions_with_regions: int
    sessions_total: int
    region_coverage_pct: float
    cache_savings_available: bool
    next_action: str
    next_action_href: str | None
    limitation: str


class RegionsAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: ContextLedgerSummary
    regions: list[RegionAggregate]
    trend: list[RegionTrendPoint]
    rebilled_blocks: list[RebilledBlock]
    cache_trend: list[CacheTrendPoint]
    agents: list[ContextAgentAggregate]
    coverage: list[ContextCoverage]
    schema_overhead_tokens: int
    schema_overhead_cost: float
    limitations: list[str]


class WasteCategory(BaseModel):
    category: str
    tokens: int
    events: int


class WasteAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    categories: list[WasteCategory]
    total_waste_tokens: int


class ToolEvidence(BaseModel):
    trace_id: str
    span_id: str
    label: str


class ToolTrendPoint(BaseModel):
    day: str
    invocations: int
    errors: int


class ToolAggregate(BaseModel):
    tool_id: str
    display_name: str
    family: str
    invocations: int
    sessions: int
    success_count: int
    error_count: int
    cancelled_count: int
    success_rate: float
    error_rate: float
    retry_rate: float
    median_latency_ms: float | None
    p95_latency_ms: float | None
    result_tokens: int
    estimated_cost_share: float
    estimate_kind: str
    trend: list[ToolTrendPoint]
    worst_session: ToolEvidence | None
    limitation: str


class ToolFailureSample(BaseModel):
    tool_id: str
    display_name: str
    status: str
    duration_ms: int | None
    evidence: ToolEvidence
    detail: str


class ToolCoverage(BaseModel):
    source: str
    sessions: int
    tool_sessions: int
    tool_coverage_pct: float
    distinct_tools: int
    mapped_tools: int
    limitation: str


class ToolsLedgerSummary(BaseModel):
    conclusion: str
    invocations: int
    distinct_tools: int
    sessions_with_tools: int
    sessions_total: int
    error_rate: float
    retry_rate: float
    schema_overhead_tokens: int
    schema_tax_estimated: bool
    next_action: str
    next_action_href: str | None
    limitation: str


class ToolsAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: ToolsLedgerSummary
    tools: list[ToolAggregate]
    failures: list[ToolFailureSample]
    coverage: list[ToolCoverage]
    schema_overhead_tokens: int
    limitations: list[str]


class FileEvidence(BaseModel):
    trace_id: str
    span_id: str
    label: str


class FileHotspot(BaseModel):
    path_rel: str
    reads: int
    re_reads: int
    edits: int
    deletes: int
    revert_fixup_sessions: int
    sessions: int
    tokens: int
    estimated_cost_share: float
    estimate_kind: str
    ignored: bool
    evidence: FileEvidence | None
    limitation: str


class FileChurnPoint(BaseModel):
    day: str
    reads: int
    edits: int
    re_reads: int


class FilesLedgerSummary(BaseModel):
    conclusion: str
    distinct_files: int
    reads: int
    re_reads: int
    edits: int
    revert_fixup_sessions: int
    ignored_files: int
    next_action: str
    next_action_href: str | None
    limitation: str


class FilesAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: FilesLedgerSummary
    files: list[FileHotspot]
    churn: list[FileChurnPoint]
    limitations: list[str]


class CompareMetricInterval(BaseModel):
    value: float | None
    ci_low: float | None
    ci_high: float | None
    sample_size: int
    sufficient: bool
    limitation: str = ""


class CompareCell(BaseModel):
    agent_id: str
    difficulty_bucket: str
    sessions: int
    cost_per_session: CompareMetricInterval
    tokens_per_session: CompareMetricInterval
    quality_mean: CompareMetricInterval
    waste_tokens_per_session: CompareMetricInterval
    retry_rate: CompareMetricInterval
    cost_per_success: CompareMetricInterval
    verification_debt_rate: CompareMetricInterval
    verified_success_rate: CompareMetricInterval
    correction_burden_rate: CompareMetricInterval
    models: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    limitation: str


class ComparePairwise(BaseModel):
    agent_a: str
    agent_b: str
    difficulty_bucket: str
    metric: str
    delta: float | None
    ci_low: float | None
    ci_high: float | None
    verdict: str
    sample_a: int
    sample_b: int
    confound_warnings: list[str] = Field(default_factory=list)
    limitation: str


class CompareLedgerSummary(BaseModel):
    conclusion: str
    buckets_with_evidence: int
    cells_total: int
    cells_sufficient: int
    min_sample: int
    declared_winner: str | None
    next_action: str
    next_action_href: str | None
    limitation: str


class CompareAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: CompareLedgerSummary
    cells: list[CompareCell]
    pairwise: list[ComparePairwise]
    confound_warnings: list[str]
    limitations: list[str]


class GuardAssociation(BaseModel):
    metric: str
    effect_estimate: float | None
    effect_ci_low: float | None
    effect_ci_high: float | None
    pre_n: int
    post_n: int
    verdict: str
    language: Literal["associated_with", "observed_after", "unavailable"]
    confound_notes: list[str] = Field(default_factory=list)
    limitation: str


class GuardEventRow(BaseModel):
    event_id: str
    occurred_at: str
    path_rel: str
    event_kind: str
    commit_sha: str | None
    parent_sha: str | None
    before_hash: str | None
    after_hash: str | None
    diff_summary: str | None
    git_state: str
    source: str
    confound_notes: list[str] = Field(default_factory=list)
    linked_experiment_id: str | None
    association: GuardAssociation | None = None
    optimize_href: str | None = None
    event_href: str


class GuardLedgerSummary(BaseModel):
    conclusion: str
    event_count: int
    associated_count: int
    confounded_count: int
    git_state: str
    next_action: str
    next_action_href: str | None
    limitation: str


class GuardAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    ledger: GuardLedgerSummary
    events: list[GuardEventRow]
    limitations: list[str]


class BudgetShareRow(BaseModel):
    key: str
    spend_usd: float
    share_pct: float
    sessions: int


class BudgetBurnLedger(BaseModel):
    conclusion: str
    budget_state: Literal["unconfigured", "healthy", "attention", "over"]
    projection_state: Literal["available", "insufficient_history"]
    next_action: str
    next_action_href: str | None
    limitation: str


class BudgetBurnResponse(BaseModel):
    timezone: str
    month_start: str
    month_end: str
    now: str
    monthly_limit_usd: float | None = None
    weekly_limit_usd: float | None = None
    daily_limit_usd: float | None = None
    month_spend_usd: float
    week_spend_usd: float
    day_spend_usd: float
    observed_active_days: int
    calendar_days_elapsed: int
    days_in_month: int
    projection_state: Literal["available", "insufficient_history"]
    linear_projected_usd: float | None = None
    trailing_7d_projected_usd: float | None = None
    projected_overrun_date: str | None = None
    budget_state: Literal["unconfigured", "healthy", "attention", "over"]
    explanation: str
    agent_shares: list[BudgetShareRow] = Field(default_factory=list)
    model_shares: list[BudgetShareRow] = Field(default_factory=list)
    ledger: BudgetBurnLedger
    limitations: list[str] = Field(default_factory=list)


class TailAnalyticsResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    tail_risk: TailRisk
    exceedances: list[float]
