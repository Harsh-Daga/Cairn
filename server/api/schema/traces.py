"""Trace list, detail, diff, label, and replay schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from server.api.schema.query import QueryFilterError, QueryFilterToken
from server.models.context_region import ContextRegion
from server.models.data_quality import DataQuality
from server.models.outcome import Diagnostic, Outcome
from server.models.span import Span
from server.models.time_range import ResolvedTimeRange
from server.models.trace import Trace


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
    duration_ms: int | None = None
    token_flow: list[int] = Field(default_factory=list)
    quality_score: float | None = None
    outcome_label: str | None = None
    verification_state: Literal["verified", "failed", "debt", "unverified", "unknown"] = "unknown"
    first_user_request: str | None = None
    top_files: list[str] = Field(default_factory=list)
    data_quality_state: Literal["measured", "partial", "degraded", "unavailable"] = "unavailable"


class TracesListResponse(BaseModel):
    traces: list[TraceRow]
    total: int
    limit: int
    offset: int
    resolved_range: ResolvedTimeRange | None = None
    filter_phrase: str = ""
    filter_tokens: list[QueryFilterToken] = Field(default_factory=list)
    filter_errors: list[QueryFilterError] = Field(default_factory=list)


class TraceDiffTurn(BaseModel):
    index: int
    op: Literal["match", "insert", "delete"]
    a: Span | None
    b: Span | None
    delta_tokens: int
    delta_waste_tokens: int
    delta_quality: float


class TraceDiffSummary(BaseModel):
    cost_a: float
    cost_b: float
    delta_cost: float
    waste_a: int
    waste_b: int
    delta_waste_tokens: int
    quality_a: float
    quality_b: float
    delta_quality: float


class TraceDiffRegion(BaseModel):
    region: str
    tokens_a: int
    tokens_b: int
    delta_tokens: int
    cost_a: float
    cost_b: float
    delta_cost: float


class TraceDiffComparability(BaseModel):
    state: Literal["comparable", "limited", "not_comparable"]
    reasons: list[str]
    facts: list[str]
    limitation: str


class TraceDiffEvidence(BaseModel):
    side: Literal["a", "b", "both"]
    label: str
    trace_id: str
    span_id: str | None = None
    evidence_type: Literal["session", "span", "diagnostic", "outcome", "region"] = "session"


class TraceDiffChange(BaseModel):
    statement: str
    basis: Literal["recorded_delta", "diagnostic", "limitation"]
    evidence: list[TraceDiffEvidence] = Field(default_factory=list)


class TraceDiffAnalysis(BaseModel):
    tokens_a: int
    tokens_b: int
    delta_tokens: int
    duration_ms_a: int | None
    duration_ms_b: int | None
    delta_duration_ms: int | None
    models_a: list[str]
    models_b: list[str]
    regions: list[TraceDiffRegion]
    outcome_a: Outcome | None
    outcome_b: Outcome | None
    diagnostic_a: Diagnostic | None
    diagnostic_b: Diagnostic | None
    alignment_mode: Literal["lcs", "bounded_position"]
    alignment_truncated: bool
    alignment_limitation: str | None
    comparability: TraceDiffComparability
    what_changed: list[TraceDiffChange]
    evidence: list[TraceDiffEvidence]


class TraceDiffResponse(BaseModel):
    a: Trace
    b: Trace
    summary: TraceDiffSummary
    turns: list[TraceDiffTurn]
    analysis: TraceDiffAnalysis


class SpanNode(BaseModel):
    span: Span
    children: list[SpanNode] = Field(default_factory=list)


class SpanLink(BaseModel):
    from_span_id: str
    to_span_id: str
    link_type: str


class McpConsultation(BaseModel):
    event_id: str
    trace_id: str
    after_seq: int
    tool_name: str
    called_at: str


class SessionShield(BaseModel):
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


class ReplaySummary(BaseModel):
    turn: int
    context_tokens: int | None
    cost: float
    cost_estimated: bool
    files_read: int
    agents: int


class PostmortemStep(BaseModel):
    kind: str
    label: str
    span_id: str | None = None
    seq: int | None = None
    summary: str
    items: list[dict[str, object]] = Field(default_factory=list)
    retry_span_ids: list[str] = Field(default_factory=list)
    waste_tokens: int | None = None
    retry_waste_tokens: int | None = None
    cascade_blast_tokens: int | None = None
    attributed_cost_usd: float | None = None


class PostmortemSpanLink(BaseModel):
    span_id: str
    href: str
    label: str


class PostmortemResponse(BaseModel):
    trace_id: str
    eligible: bool
    source: Literal["diagnose_cascade"]
    reflector: None = None
    primary_category: str | None = None
    secondary_category: str | None = None
    failure_signature: str | None = None
    outcome_label: str | None = None
    quality_score: float | None = None
    steps: list[PostmortemStep] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    span_links: list[PostmortemSpanLink] = Field(default_factory=list)
    markdown: str
    limitation: str


class ReceiptIntent(BaseModel):
    present: bool
    span_id: str | None = None
    summary: str | None = None
    limitation: str | None = None


class ReceiptRequirement(BaseModel):
    id: str
    text: str
    status: Literal["supported", "unsupported", "contradicted", "unverified"]
    span_id: str | None = None


class ReceiptClaim(BaseModel):
    id: str
    text: str
    status: Literal["supported", "unsupported", "contradicted", "unverified"]
    span_ids: list[str] = Field(default_factory=list)


class ReceiptEvidenceRef(BaseModel):
    kind: str
    span_id: str | None = None
    label: str


class ReceiptTimelineEvent(BaseModel):
    kind: str
    at: str
    span_id: str | None = None
    summary: str


class ReceiptDebtComponent(BaseModel):
    id: str
    weight: float
    active: bool
    reason: str


class ReceiptDebt(BaseModel):
    score: float
    components: list[ReceiptDebtComponent]
    explanation: str


class ReceiptOutcomeSummary(BaseModel):
    label: str | None = None
    tests_run: int | None = None
    tests_passed: int | None = None
    tests_failed: int | None = None
    build_status: str | None = None
    human_label: str | None = None
    quality_score: float | None = None


class ReceiptRiskFinding(BaseModel):
    rule_id: str
    risk: str
    message: str
    enforcement_source: Literal["observed_violation", "advisory_warning", "allowlisted_exception"]
    evidence: dict[str, object] = Field(default_factory=dict)


class ReceiptRiskPolicy(BaseModel):
    evaluated: bool
    review_risk: Literal["none", "low", "medium", "high"] = "none"
    findings: list[ReceiptRiskFinding] = Field(default_factory=list)
    limitation: str
    enforcement_note: str | None = None


class ReceiptResponse(BaseModel):
    schema_version: str
    builder_version: str
    trace_id: str
    status: Literal["verified", "failed", "debt", "unverified", "unknown"]
    intent: ReceiptIntent
    requirements: list[ReceiptRequirement] = Field(default_factory=list)
    claims: list[ReceiptClaim] = Field(default_factory=list)
    claims_limitation: str
    evidence: list[ReceiptEvidenceRef] = Field(default_factory=list)
    timeline: list[ReceiptTimelineEvent] = Field(default_factory=list)
    debt: ReceiptDebt
    outcome: ReceiptOutcomeSummary
    risk_policy: ReceiptRiskPolicy
    limitations: list[str] = Field(default_factory=list)
    content_hash: str
    markdown: str | None = None
    persisted: bool = False


class CorrectionEvent(BaseModel):
    correction_id: str
    span_id: str
    seq: int
    classification: str
    original_class: str
    confidence: Literal["high", "medium", "low"]
    signal: str
    excerpt: str
    recovery_status: Literal["recovered", "unresolved", "unknown"]
    recovery_span_id: str | None = None
    user_relabel: dict[str, object] | None = None
    kind: str = "observed_phrase_match"


class CorrectionsResponse(BaseModel):
    schema_version: str
    builder_version: str
    trace_id: str
    correction_count: int
    unresolved_count: int
    corrections: list[CorrectionEvent] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ranking_forbidden: bool = True
    content_hash: str
    persisted: bool = False


class CorrectionRelabelRequest(BaseModel):
    relabel_class: Literal[
        "project_reading_failure",
        "intent_misunderstanding",
        "instruction_rule_violation",
        "scope_boundary_violation",
        "implementation_failure",
        "execution_verification_failure",
        "misleading_progress_reporting",
        "unclassified",
        "not_a_correction",
    ]
    note: str | None = Field(default=None, max_length=1000)


class HandoffStatement(BaseModel):
    kind: Literal["fact", "inference", "recommendation"]
    text: str
    span_id: str | None = None


class HandoffSection(BaseModel):
    id: str
    title: str
    items: list[HandoffStatement] = Field(default_factory=list)


class HandoffResponse(BaseModel):
    schema_version: str
    builder_version: str
    trace_id: str
    char_budget: int
    truncated: bool
    sections: list[HandoffSection] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    content_hash: str
    markdown: str | None = None


class TraceDetailResponse(BaseModel):
    trace: Trace
    spans: list[Span]
    tree: list[SpanNode]
    links: list[SpanLink]
    mcp_consultations: list[McpConsultation]
    regions: list[ContextRegion]
    diagnostics: Diagnostic | None
    quality: DataQuality | None
    outcome: Outcome | None
    shields: list[SessionShield] = Field(default_factory=list)
    postmortem: PostmortemResponse | None = None
    receipt: ReceiptResponse | None = None
    corrections: CorrectionsResponse | None = None
    handoff: HandoffResponse | None = None


class HumanLabelRequest(BaseModel):
    label: Literal["up", "down"] | None
    note: str | None = Field(default=None, max_length=1000)


class HumanLabelResponse(BaseModel):
    trace_id: str
    label: Literal["up", "down"] | None
    note: str | None
    labeled_at: str | None


class ReplayCheckpoint(BaseModel):
    seq: int
    spans: list[Span]
    summary: ReplaySummary


class ReplayResponse(BaseModel):
    trace_id: str
    seq: int | None = None
    max_seq: int | None = None
    step: int | None = None
    spans: list[Span] | None = None
    summary: ReplaySummary | None = None
    checkpoints: list[ReplayCheckpoint] | None = None
