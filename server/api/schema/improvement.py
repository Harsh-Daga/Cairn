"""Insight evidence and experiment schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, JsonValue

from server.models.experiment import Experiment, VerdictHistoryEntry
from server.models.insight import InsightLifecycle, InsightSeverity
from server.models.span import Span


class InsightFix(BaseModel):
    kind: str
    label: str
    value: str


class InsightRow(BaseModel):
    insight_id: str
    fingerprint: str
    detector: str
    severity: InsightSeverity
    title: str
    body: str
    state: InsightLifecycle
    savings_estimate: float | None
    savings_unavailable_reason: str | None
    fix: InsightFix
    diagnostic: bool
    action: str | None
    last_seen_at: str
    rank_score: float = 0.0
    impact: float | None = None
    confidence: Literal["low", "medium"] = "low"
    recurrence: int = 1
    snoozed_until: str | None = None
    suppressed_duplicate: bool = False


class InsightsLedgerSummary(BaseModel):
    conclusion: str
    open_count: int
    ranked_count: int
    snoozed_count: int
    suppressed_duplicates: int
    top_insight_id: str | None
    next_action: str
    next_action_href: str | None
    limitation: str


class InsightsResponse(BaseModel):
    ledger: InsightsLedgerSummary
    insights: list[InsightRow]
    total: int
    limitations: list[str]


class EvidenceChainResponse(BaseModel):
    insight_id: str
    evidence_id: str
    producer: str
    produced_at: str
    trace_ids: list[str]
    span_ids: list[str] | None
    metrics: dict[str, JsonValue]
    spans: list[Span]


class ExperimentRow(BaseModel):
    experiment_id: str
    status: str
    target_file: str | None
    created_at: str
    applied_at: str | None
    min_holdout: int
    outcome_n_effective: float | None
    outcome_n_raw: int | None = None
    sample_size: float | None = None
    verdict: str | None
    plain_verdict: str | None = None
    lift_pct: float | None
    effect_ci_low: float | None
    effect_ci_high: float | None
    measured_at: str | None
    last_evaluated_at: str | None = None
    eval_interval_days: int = 30
    proposal_source: str = "local"
    decay_state: str = "unknown"
    confound_flag: bool = False
    confound_notes: list[str] = Field(default_factory=list)
    effect_history: list[float] = Field(default_factory=list)
    verdict_history: list[VerdictHistoryEntry] = Field(default_factory=list)
    regression_outside_interval: bool = False
    guard_event_id: str | None = None
    in_portfolio: bool = False


class OptimizeLedgerSummary(BaseModel):
    conclusion: str
    proposed_count: int
    active_count: int
    portfolio_count: int
    decayed_count: int
    next_action: str
    next_action_href: str | None
    limitation: str


class ExperimentsResponse(BaseModel):
    ledger: OptimizeLedgerSummary
    experiments: list[ExperimentRow]
    limitations: list[str]


class VerdictPreviewData(BaseModel):
    expected_days_to_verdict: float | None
    traces_per_day: float
    n_effective_needed: float
    traffic_unknown: bool


class ExperimentDetailResponse(BaseModel):
    experiment: Experiment
    preview: VerdictPreviewData | None = None
    write_safety: str
    guard_limitation: str
