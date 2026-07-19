"""Overview and recap response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from server.models.time_range import ResolvedTimeRange


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


class OverviewEvidence(BaseModel):
    trace_id: str
    span_id: str | None = None
    label: str
    path_rel: str | None = None
    waste_tokens: int = 0


class WasteCause(BaseModel):
    category: str
    waste_tokens: int
    estimated_savings_usd: float
    cause: str
    fix: str
    confidence: Literal["low", "medium"] = "low"
    confidence_explanation: str = "Insufficient supporting evidence for a stronger label."
    evidence_count: int = 0
    evidence: list[OverviewEvidence] = Field(default_factory=list)


class MetricDelta(BaseModel):
    current: float | int | None
    previous: float | int | None
    delta_pct: float | None
    state: Literal["available", "no_previous", "unavailable"]


class MonthEndProjection(BaseModel):
    state: Literal["available", "insufficient_history", "not_current_period"]
    projected_usd: float | None = None
    trailing_7d_projected_usd: float | None = None
    projected_overrun_date: str | None = None
    month_spend_usd: float
    observed_active_days: int
    calendar_days_elapsed: int
    days_in_month: int
    explanation: str


class BudgetSummary(BaseModel):
    state: Literal["unconfigured", "healthy", "attention", "over"]
    monthly_limit_usd: float | None = None
    weekly_limit_usd: float | None = None
    daily_limit_usd: float | None = None
    month_spend_usd: float
    week_spend_usd: float = 0.0
    day_spend_usd: float = 0.0
    projected_usd: float | None = None
    trailing_7d_projected_usd: float | None = None
    projected_overrun_date: str | None = None
    explanation: str


class OverviewHero(BaseModel):
    quality_mean: float | None
    quality_sessions: int
    cost_per_success_usd: float | None
    successful_sessions: int
    quality_sparkline: list[float] = Field(default_factory=list)
    projection: MonthEndProjection
    budget: BudgetSummary
    deltas: dict[str, MetricDelta]


class ShieldSummary(BaseModel):
    shield: Literal["verification", "scope", "privacy", "resource"]
    state: Literal[
        "healthy",
        "degraded",
        "paused",
        "quarantined",
        "attention",
        "unknown",
        "unavailable",
    ]
    summary: str
    facts: list[str]
    limitation: str
    action_label: str
    action_path: str


class TrendAnnotation(BaseModel):
    occurred_at: str
    label: str
    kind: Literal["experiment", "guard"]
    action_path: str


class OverviewAttentionItem(BaseModel):
    item_id: str
    title: str
    detail: str
    action_path: str


class OverviewAttentionCategory(BaseModel):
    category: Literal[
        "failed_outcomes",
        "verification_debt",
        "unsupported_claims",
        "drift",
        "retry_storms",
        "parse_health",
        "budget",
        "decayed_rules",
    ]
    label: str
    state: Literal["attention", "clear", "unavailable"]
    count: int
    summary: str
    limitation: str | None = None
    items: list[OverviewAttentionItem] = Field(default_factory=list)


class MoneySummary(BaseModel):
    period_days: int
    total_spend_usd: float
    spend_estimated: bool
    wasted_spend_usd: float
    wasted_spend_pct: float
    waste_estimated: bool
    top_causes: list[WasteCause]
    primary_action: str


class OverviewResponse(BaseModel):
    days: int
    resolved_range: ResolvedTimeRange
    kpis: dict[str, float | int | None]
    money: MoneySummary
    hero: OverviewHero
    shields: list[ShieldSummary]
    annotations: list[TrendAnnotation]
    attention: list[OverviewAttentionCategory] = Field(default_factory=list)
    narrative: list[NarrativeSentence]
    tail_risk: TailRisk
    data_notes: list[DataNote]


class QualityTrend(BaseModel):
    current_mean: float | None
    previous_mean: float | None
    delta: float | None
    current_sessions: int
    previous_sessions: int


class RecapVerdict(BaseModel):
    experiment_id: str
    verdict: str
    effect_estimate: float | None
    effect_ci_low: float | None
    effect_ci_high: float | None
    measured_at: str


class RecapSessionHighlight(BaseModel):
    trace_id: str
    title: str
    metric: str
    value: float
    href: str


class RecapDecayedRule(BaseModel):
    experiment_id: str
    target_file: str | None
    decay_state: str
    plain_verdict: str | None
    href: str


class RecapGuardEvent(BaseModel):
    event_id: str
    occurred_at: str
    path_rel: str
    event_kind: str
    href: str


class RecapRecommendedAction(BaseModel):
    label: str
    href: str
    reason: str


class RecapResponse(BaseModel):
    generated_at: str
    period_days: int
    period_start: str
    period_end: str
    timezone: str = "UTC"
    period_kind: Literal["rolling_7d"] = "rolling_7d"
    money: MoneySummary
    quality_trend: QualityTrend
    cost_per_success_trend: QualityTrend
    experiment_verdicts: list[RecapVerdict]
    decayed_rules: list[RecapDecayedRule] = Field(default_factory=list)
    guard_events: list[RecapGuardEvent] = Field(default_factory=list)
    best_session: RecapSessionHighlight | None = None
    worst_session: RecapSessionHighlight | None = None
    recommended_action: RecapRecommendedAction | None = None
    limitations: list[str] = Field(default_factory=list)
