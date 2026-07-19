/** Auto-generated from FastAPI OpenAPI — do not edit by hand. */
/** Regenerate via `uv run python scripts/build_ui.py types`. */

export interface ActionManifestEntry {
  name: string;
  title: string;
  category: string;
  params_schema: Record<string, JsonValue>;
  async_job: boolean;
}

export interface ActionResultResponse {
  ok: boolean;
  result: Record<string, JsonValue> | null;
  job_id: string | null;
}

export interface ActionsManifestResponse {
  actions: ActionManifestEntry[];
}

export interface AdapterWarning {
  adapter_id: string;
  message: string;
  issue_url: string;
}

export interface AgentAggregate {
  agent_id: string | null;
  actor_id: string | null;
  actor_name: string | null;
  traces: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  waste_tokens: number;
  quality_mean: number | null;
  quality_samples: number;
  error_sessions: number;
  models: string[];
  sources: string[];
  fingerprint_thumbnail: number[] | null;
  fingerprint_samples: number;
  sample_size: number;
}

export interface AgentParseCoverage {
  source: string;
  sessions: number;
  attempts: number;
  fully_parsed: number;
  degraded: number;
  skipped: number;
  parse_success_pct: number | null;
  limitation: string;
}

export interface AgentTrendPoint {
  day: string;
  agent_id: string;
  traces: number;
  cost: number;
  waste_tokens: number;
}

export interface AgentsLedgerSummary {
  conclusion: string;
  agent_count: number;
  multi_agent_sessions: number;
  handoffs: number;
  sample_size: number;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface AgentsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: AgentsLedgerSummary;
  agents: AgentAggregate[];
  handoff_matrix: HandoffRow[];
  trend: AgentTrendPoint[];
  coverage: AgentParseCoverage[];
  limitations: string[];
}

export interface BaselineProgress {
  collected: number;
  required: number;
  ready: boolean;
  note: string;
}

export interface BehaviorLedgerSummary {
  conclusion: string;
  fingerprint_sessions: number;
  drift_events: number;
  baseline_ready: boolean;
  baseline_collected: number;
  baseline_required: number;
  primary_axis: string | null;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface BehaviorRadar {
  project: string;
  model: string;
  week: string;
  mean_vector: number[];
  cov_inv: number[][];
  n: number;
  axes: RadarAxis[];
}

export interface BehaviorResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: BehaviorLedgerSummary;
  series: BehaviorSeriesPoint[];
  drift: DriftEvent[];
  radar: BehaviorRadar | null;
  baseline_progress: BaselineProgress;
  data_notes: DataNote[];
  limitations: string[];
}

export interface BehaviorSeriesPoint {
  trace_id: string;
  ts: string | null;
  vector: number[];
  project: string | null;
  model: string | null;
}

export interface BudgetBurnLedger {
  conclusion: string;
  budget_state: "unconfigured" | "healthy" | "attention" | "over";
  projection_state: "available" | "insufficient_history";
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface BudgetBurnResponse {
  timezone: string;
  month_start: string;
  month_end: string;
  now: string;
  monthly_limit_usd: number | null;
  weekly_limit_usd: number | null;
  daily_limit_usd: number | null;
  month_spend_usd: number;
  week_spend_usd: number;
  day_spend_usd: number;
  observed_active_days: number;
  calendar_days_elapsed: number;
  days_in_month: number;
  projection_state: "available" | "insufficient_history";
  linear_projected_usd: number | null;
  trailing_7d_projected_usd: number | null;
  projected_overrun_date: string | null;
  budget_state: "unconfigured" | "healthy" | "attention" | "over";
  explanation: string;
  agent_shares: BudgetShareRow[];
  model_shares: BudgetShareRow[];
  ledger: BudgetBurnLedger;
  limitations: string[];
}

export interface BudgetShareRow {
  key: string;
  spend_usd: number;
  share_pct: number;
  sessions: number;
}

export interface BudgetSummary {
  state: "unconfigured" | "healthy" | "attention" | "over";
  monthly_limit_usd: number | null;
  weekly_limit_usd: number | null;
  daily_limit_usd: number | null;
  month_spend_usd: number;
  week_spend_usd: number;
  day_spend_usd: number;
  projected_usd: number | null;
  trailing_7d_projected_usd: number | null;
  projected_overrun_date: string | null;
  explanation: string;
}

export interface CacheTrendPoint {
  day: string;
  input_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  measured_sessions: number;
  total_sessions: number;
  hit_ratio: number | null;
  estimated_savings_usd: number | null;
  limitation: string;
}

export interface CollectionStatus {
  mode: "manual" | "efficient" | "live";
  label: string;
  auto_sync_active: boolean;
  watcher_enabled: boolean;
  refresh_enabled: boolean;
  poll_interval_sec: number;
  refresh_interval_sec: number;
  limitation: string;
  live_updates_note: string;
}

export interface CompareAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: CompareLedgerSummary;
  cells: CompareCell[];
  pairwise: ComparePairwise[];
  confound_warnings: string[];
  limitations: string[];
}

export interface CompareCell {
  agent_id: string;
  difficulty_bucket: string;
  sessions: number;
  cost_per_session: CompareMetricInterval;
  tokens_per_session: CompareMetricInterval;
  quality_mean: CompareMetricInterval;
  waste_tokens_per_session: CompareMetricInterval;
  retry_rate: CompareMetricInterval;
  cost_per_success: CompareMetricInterval;
  verification_debt_rate: CompareMetricInterval;
  verified_success_rate: CompareMetricInterval;
  correction_burden_rate: CompareMetricInterval;
  models: string[];
  sources: string[];
  limitation: string;
}

export interface CompareLedgerSummary {
  conclusion: string;
  buckets_with_evidence: number;
  cells_total: number;
  cells_sufficient: number;
  min_sample: number;
  declared_winner: string | null;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface CompareMetricInterval {
  value: number | null;
  ci_low: number | null;
  ci_high: number | null;
  sample_size: number;
  sufficient: boolean;
  limitation: string;
}

export interface ComparePairwise {
  agent_a: string;
  agent_b: string;
  difficulty_bucket: string;
  metric: string;
  delta: number | null;
  ci_low: number | null;
  ci_high: number | null;
  verdict: string;
  sample_a: number;
  sample_b: number;
  confound_warnings: string[];
  limitation: string;
}

export interface ContextAgentAggregate {
  agent_id: string;
  sessions: number;
  spans: number;
  tokens: number;
  cost: number;
  top_region: string | null;
}

export interface ContextCoverage {
  source: string;
  sessions: number;
  region_sessions: number;
  region_coverage_pct: number;
  cache_measured_sessions: number;
  cache_coverage_pct: number;
  timestamp_sessions: number;
  dropped_events: number;
  limitation: string;
}

export interface ContextEvidence {
  trace_id: string;
  span_id: string;
  region: string;
  label: string;
}

export interface ContextLedgerSummary {
  conclusion: string;
  mapped_region_tokens: number;
  mapped_region_cost: number;
  estimated_rebilled_tokens: number;
  schema_overhead_tokens: number;
  tool_result_share: number;
  repetition_intensity: number | null;
  primary_region: string | null;
  sessions_with_regions: number;
  sessions_total: number;
  region_coverage_pct: number;
  cache_savings_available: boolean;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface ContextRegion {
  span_id: string;
  region: "system" | "tool_schema" | "tool_result" | "retrieved" | "user" | "history";
  tokens: number;
  cost: number;
  content_hash: string | null;
  first_turn: number | null;
  last_seen_turn: number | null;
  still_in_window: boolean;
}

export interface CorrectionEvent {
  correction_id: string;
  span_id: string;
  seq: number;
  classification: string;
  original_class: string;
  confidence: "high" | "medium" | "low";
  signal: string;
  excerpt: string;
  recovery_status: "recovered" | "unresolved" | "unknown";
  recovery_span_id: string | null;
  user_relabel: Record<string, unknown> | null;
  kind: string;
}

export interface CorrectionRelabelRequest {
  relabel_class: "project_reading_failure" | "intent_misunderstanding" | "instruction_rule_violation" | "scope_boundary_violation" | "implementation_failure" | "execution_verification_failure" | "misleading_progress_reporting" | "unclassified" | "not_a_correction";
  note: string | null;
}

export interface CorrectionsResponse {
  schema_version: string;
  builder_version: string;
  trace_id: string;
  correction_count: number;
  unresolved_count: number;
  corrections: CorrectionEvent[];
  limitations: string[];
  ranking_forbidden: boolean;
  content_hash: string;
  persisted: boolean;
}

export interface CostPerSuccessPoint {
  trace_id: string;
  day: string;
  cost_per_success: number;
}

export interface DataNote {
  source: string;
  sessions: number;
  issue: string;
  message: string;
  help_url: string | null;
}

export interface DataQuality {
  trace_id: string;
  pct_tokens_measured: number | null;
  pct_tokens_estimated: number | null;
  timestamps_present: boolean;
  cost_source: string;
  parser_version: string | null;
  dropped_events: number;
  notes: Record<string, unknown>;
  computed_at: string | null;
}

export interface Diagnostic {
  trace_id: string;
  failure_origin_span_id: string | null;
  failure_signature: string | null;
  primary_category: string | null;
  secondary_category: string | null;
  cascade_root_span_id: string | null;
  cascade_blast_tokens: number | null;
  ideal_path_savings_tokens: number | null;
  computed_at: string | null;
}

export interface DriftAxis {
  axis: number;
  axis_label: string;
  weeks_outside: number;
  ewma: number;
  bounds: number[];
}

export interface DriftEvent {
  kind: string;
  trace_id: string | null;
  project: string | null;
  model: string | null;
  distance: number | null;
  threshold: number | null;
  per_dim_deltas: number[];
  drift: boolean | null;
  axes: DriftAxis[];
  data_notes: string[];
  sample_size: number;
  drifted_at: string | null;
  magnitude: number | null;
}

export interface ErrorDetail {
  code: string;
  message: string;
  details: JsonValue | null;
}

export interface ErrorResponse {
  error: ErrorDetail;
}

export interface EvidenceChainResponse {
  insight_id: string;
  evidence_id: string;
  producer: string;
  produced_at: string;
  trace_ids: string[];
  span_ids: string[] | null;
  metrics: Record<string, JsonValue>;
  spans: Span[];
}

export interface Experiment {
  experiment_id: string;
  created_at: string;
  target_file: string;
  block_key: string;
  kind: string;
  content: string;
  evidence_id: string;
  status: "proposed" | "applied" | "measuring" | "verdict" | "reverted" | "rejected";
  applied_at: string | null;
  min_holdout: number;
  baseline_metric: number | null;
  baseline_n_effective: number | null;
  baseline_n_raw: number | null;
  outcome_metric: number | null;
  outcome_n_effective: number | null;
  outcome_n_raw: number | null;
  effect_estimate: number | null;
  effect_ci_low: number | null;
  effect_ci_high: number | null;
  test_method: string | null;
  verdict: string | null;
  confound_flag: boolean;
  measured_at: string | null;
  agent_type: string | null;
  proposal_source: "local" | "provider";
  decay_state: "healthy" | "decaying" | "decayed" | "unknown";
  last_evaluated_at: string | null;
  plain_verdict: string | null;
  confound_notes: string[];
  effect_history: number[];
  guard_event_id: string | null;
  eval_interval_days: number;
  verdict_history: VerdictHistoryEntry[];
  regression_outside_interval: boolean;
}

export interface ExperimentDetailResponse {
  experiment: Experiment;
  preview: VerdictPreviewData | null;
  write_safety: string;
  guard_limitation: string;
}

export interface ExperimentRow {
  experiment_id: string;
  status: string;
  target_file: string | null;
  created_at: string;
  applied_at: string | null;
  min_holdout: number;
  outcome_n_effective: number | null;
  outcome_n_raw: number | null;
  sample_size: number | null;
  verdict: string | null;
  plain_verdict: string | null;
  lift_pct: number | null;
  effect_ci_low: number | null;
  effect_ci_high: number | null;
  measured_at: string | null;
  last_evaluated_at: string | null;
  eval_interval_days: number;
  proposal_source: string;
  decay_state: string;
  confound_flag: boolean;
  confound_notes: string[];
  effect_history: number[];
  verdict_history: VerdictHistoryEntry[];
  regression_outside_interval: boolean;
  guard_event_id: string | null;
  in_portfolio: boolean;
}

export interface ExperimentsResponse {
  ledger: OptimizeLedgerSummary;
  experiments: ExperimentRow[];
  limitations: string[];
}

export interface FileChurnPoint {
  day: string;
  reads: number;
  edits: number;
  re_reads: number;
}

export interface FileEvidence {
  trace_id: string;
  span_id: string;
  label: string;
}

export interface FileHotspot {
  path_rel: string;
  reads: number;
  re_reads: number;
  edits: number;
  deletes: number;
  revert_fixup_sessions: number;
  sessions: number;
  tokens: number;
  estimated_cost_share: number;
  estimate_kind: string;
  ignored: boolean;
  evidence: FileEvidence | null;
  limitation: string;
}

export interface FilesAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: FilesLedgerSummary;
  files: FileHotspot[];
  churn: FileChurnPoint[];
  limitations: string[];
}

export interface FilesLedgerSummary {
  conclusion: string;
  distinct_files: number;
  reads: number;
  re_reads: number;
  edits: number;
  revert_fixup_sessions: number;
  ignored_files: number;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface GuardAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: GuardLedgerSummary;
  events: GuardEventRow[];
  limitations: string[];
}

export interface GuardAssociation {
  metric: string;
  effect_estimate: number | null;
  effect_ci_low: number | null;
  effect_ci_high: number | null;
  pre_n: number;
  post_n: number;
  verdict: string;
  language: "associated_with" | "observed_after" | "unavailable";
  confound_notes: string[];
  limitation: string;
}

export interface GuardEventRow {
  event_id: string;
  occurred_at: string;
  path_rel: string;
  event_kind: string;
  commit_sha: string | null;
  parent_sha: string | null;
  before_hash: string | null;
  after_hash: string | null;
  diff_summary: string | null;
  git_state: string;
  source: string;
  confound_notes: string[];
  linked_experiment_id: string | null;
  association: GuardAssociation | null;
  optimize_href: string | null;
  event_href: string;
}

export interface GuardLedgerSummary {
  conclusion: string;
  event_count: number;
  associated_count: number;
  confounded_count: number;
  git_state: string;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface HandoffResponse {
  schema_version: string;
  builder_version: string;
  trace_id: string;
  char_budget: number;
  truncated: boolean;
  sections: HandoffSection[];
  limitations: string[];
  content_hash: string;
  markdown: string | null;
}

export interface HandoffRow {
  from_span_id: string;
  to_span_id: string;
  link_type: string;
  from_agent: string | null;
  to_agent: string | null;
}

export interface HandoffSection {
  id: string;
  title: string;
  items: HandoffStatement[];
}

export interface HandoffStatement {
  kind: "fact" | "inference" | "recommendation";
  text: string;
  span_id: string | null;
}

export interface HumanLabelAgreement {
  labeled_sessions: number;
  agreements: number;
  rate: number | null;
}

export interface HumanLabelRequest {
  label: "up" | "down" | null;
  note?: string | null;
}

export interface HumanLabelResponse {
  trace_id: string;
  label: "up" | "down" | null;
  note: string | null;
  labeled_at: string | null;
}

export interface InsightFix {
  kind: string;
  label: string;
  value: string;
}

export interface InsightRow {
  insight_id: string;
  fingerprint: string;
  detector: string;
  severity: "info" | "suggestion" | "warning" | "error";
  title: string;
  body: string;
  state: "new" | "ack" | "fixed" | "regressed" | "muted";
  savings_estimate: number | null;
  savings_unavailable_reason: string | null;
  fix: InsightFix;
  diagnostic: boolean;
  action: string | null;
  last_seen_at: string;
  rank_score: number;
  impact: number | null;
  confidence: "low" | "medium";
  recurrence: number;
  snoozed_until: string | null;
  suppressed_duplicate: boolean;
}

export interface InsightsLedgerSummary {
  conclusion: string;
  open_count: number;
  ranked_count: number;
  snoozed_count: number;
  suppressed_duplicates: number;
  top_insight_id: string | null;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface InsightsResponse {
  ledger: InsightsLedgerSummary;
  insights: InsightRow[];
  total: number;
  limitations: string[];
}

export type JsonValue = unknown;

export interface McpConsultation {
  event_id: string;
  trace_id: string;
  after_seq: number;
  tool_name: string;
  called_at: string;
}

export interface MetricDelta {
  current: number | null;
  previous: number | null;
  delta_pct: number | null;
  state: "available" | "no_previous" | "unavailable";
}

export interface MoneySummary {
  period_days: number;
  total_spend_usd: number;
  spend_estimated: boolean;
  wasted_spend_usd: number;
  wasted_spend_pct: number;
  waste_estimated: boolean;
  top_causes: WasteCause[];
  primary_action: string;
}

export interface MonthEndProjection {
  state: "available" | "insufficient_history" | "not_current_period";
  projected_usd: number | null;
  trailing_7d_projected_usd: number | null;
  projected_overrun_date: string | null;
  month_spend_usd: number;
  observed_active_days: number;
  calendar_days_elapsed: number;
  days_in_month: number;
  explanation: string;
}

export interface NarrativeSentence {
  text: string;
  filter: Record<string, string> | null;
}

export interface OptimizeLedgerSummary {
  conclusion: string;
  proposed_count: number;
  active_count: number;
  portfolio_count: number;
  decayed_count: number;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface Outcome {
  trace_id: string;
  commit_sha: string | null;
  commit_landed: boolean;
  files_changed: string[] | null;
  tests_run: number | null;
  tests_passed: number | null;
  tests_failed: number | null;
  build_status: string | null;
  quality_score: number | null;
  quality_components: Record<string, number> | null;
  quality_weights: Record<string, number> | null;
  cost_per_success: number | null;
  reverted_within_window: boolean;
  fixup_within_window: boolean;
  outcome_label: string | null;
  label_source: string | null;
  human_label: "up" | "down" | null;
  human_note: string | null;
  human_labeled_at: string | null;
  captured_at: string | null;
}

export interface OverviewAttentionCategory {
  category: "failed_outcomes" | "verification_debt" | "unsupported_claims" | "drift" | "retry_storms" | "parse_health" | "budget" | "decayed_rules";
  label: string;
  state: "attention" | "clear" | "unavailable";
  count: number;
  summary: string;
  limitation: string | null;
  items: OverviewAttentionItem[];
}

export interface OverviewAttentionItem {
  item_id: string;
  title: string;
  detail: string;
  action_path: string;
}

export interface OverviewEvidence {
  trace_id: string;
  span_id: string | null;
  label: string;
  path_rel: string | null;
  waste_tokens: number;
}

export interface OverviewHero {
  quality_mean: number | null;
  quality_sessions: number;
  cost_per_success_usd: number | null;
  successful_sessions: number;
  quality_sparkline: number[];
  projection: MonthEndProjection;
  budget: BudgetSummary;
  deltas: Record<string, MetricDelta>;
}

export interface OverviewResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  kpis: Record<string, number | null>;
  money: MoneySummary;
  hero: OverviewHero;
  shields: ShieldSummary[];
  annotations: TrendAnnotation[];
  attention: OverviewAttentionCategory[];
  narrative: NarrativeSentence[];
  tail_risk: TailRisk;
  data_notes: DataNote[];
}

export interface PlanWindowGauge {
  window_hours: number;
  total_tokens: number;
  by_source: Record<string, number>;
  limit: number | null;
  exceeded: boolean;
}

export interface PostmortemResponse {
  trace_id: string;
  eligible: boolean;
  source: string;
  reflector: null;
  primary_category: string | null;
  secondary_category: string | null;
  failure_signature: string | null;
  outcome_label: string | null;
  quality_score: number | null;
  steps: PostmortemStep[];
  uncertainty: string[];
  span_links: PostmortemSpanLink[];
  markdown: string;
  limitation: string;
}

export interface PostmortemSpanLink {
  span_id: string;
  href: string;
  label: string;
}

export interface PostmortemStep {
  kind: string;
  label: string;
  span_id: string | null;
  seq: number | null;
  summary: string;
  items: Record<string, unknown>[];
  retry_span_ids: string[];
  waste_tokens: number | null;
  retry_waste_tokens: number | null;
  cascade_blast_tokens: number | null;
  attributed_cost_usd: number | null;
}

export interface QualityCalibration {
  scored_sessions: number;
  outcome_sessions: number;
  coverage_pct: number;
  human_labeled: number;
  human_agreements: number;
  human_agreement_rate: number | null;
  limitation: string;
}

export interface QualityComponentSummary {
  name: string;
  mean: number;
  weight: number;
  samples: number;
}

export interface QualityHistogramBucket {
  bucket: string;
  count: number;
}

export interface QualityInvestigation {
  kind: string;
  trace_id: string;
  quality_score: number | null;
  outcome_label: string | null;
  human_label: string | null;
  reason: string;
  limitation: string;
}

export interface QualityLedgerSummary {
  conclusion: string;
  outcome_sessions: number;
  scored_sessions: number;
  quality_mean: number | null;
  verified_completion_rate: number | null;
  verification_debt_rate: number | null;
  unsupported_claim_rate: number | null;
  mean_cost_per_success: number | null;
  lucky_pass_count: number;
  unlucky_fail_count: number;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface QualityOutcome {
  trace_id: string;
  commit_sha: string | null;
  commit_landed: boolean;
  files_changed: string[] | null;
  tests_run: number | null;
  tests_passed: number | null;
  tests_failed: number | null;
  build_status: string | null;
  quality_score: number | null;
  quality_components: Record<string, number> | null;
  quality_weights: Record<string, number> | null;
  cost_per_success: number | null;
  reverted_within_window: boolean;
  fixup_within_window: boolean;
  outcome_label: string | null;
  label_source: string | null;
  human_label: "up" | "down" | null;
  human_note: string | null;
  human_labeled_at: string | null;
  captured_at: string | null;
  cost: number;
  verification_state: string;
  day: string | null;
}

export interface QualityResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: QualityLedgerSummary;
  outcomes: QualityOutcome[];
  histogram: QualityHistogramBucket[];
  cost_per_success: CostPerSuccessPoint[];
  trend: QualityTrendPoint[];
  components: QualityComponentSummary[];
  investigations: QualityInvestigation[];
  calibration: QualityCalibration;
  data_notes: DataNote[];
  limitations: string[];
}

export interface QualityTrend {
  current_mean: number | null;
  previous_mean: number | null;
  delta: number | null;
  current_sessions: number;
  previous_sessions: number;
}

export interface QualityTrendPoint {
  day: string;
  quality_mean: number | null;
  quality_samples: number;
  verified_rate: number | null;
  debt_rate: number | null;
  human_up: number;
  human_down: number;
  mean_cost_per_success: number | null;
}

export interface QueryFilterError {
  token: string;
  message: string;
}

export interface QueryFilterToken {
  raw: string;
  field: "agent" | "source" | "status" | "cost" | "outcome" | "file" | "tool" | "after" | "claim" | "verification" | "corrected" | "risk";
  value: string;
  comparison: "eq" | "gt" | "gte" | "lt" | "lte";
  available: boolean;
}

export interface RadarAxis {
  axis: string;
  value: number;
}

export interface RebilledBlock {
  block_id: string;
  region: string;
  occurrences: number;
  sessions: number;
  tokens: number;
  estimated_rebilled_tokens: number;
  cost: number;
  suggested_fix: string;
  evidence: ContextEvidence;
  limitation: string;
}

export interface RecapDecayedRule {
  experiment_id: string;
  target_file: string | null;
  decay_state: string;
  plain_verdict: string | null;
  href: string;
}

export interface RecapGuardEvent {
  event_id: string;
  occurred_at: string;
  path_rel: string;
  event_kind: string;
  href: string;
}

export interface RecapRecommendedAction {
  label: string;
  href: string;
  reason: string;
}

export interface RecapResponse {
  generated_at: string;
  period_days: number;
  period_start: string;
  period_end: string;
  timezone: string;
  period_kind: string;
  money: MoneySummary;
  quality_trend: QualityTrend;
  cost_per_success_trend: QualityTrend;
  experiment_verdicts: RecapVerdict[];
  decayed_rules: RecapDecayedRule[];
  guard_events: RecapGuardEvent[];
  best_session: RecapSessionHighlight | null;
  worst_session: RecapSessionHighlight | null;
  recommended_action: RecapRecommendedAction | null;
  limitations: string[];
}

export interface RecapSessionHighlight {
  trace_id: string;
  title: string;
  metric: string;
  value: number;
  href: string;
}

export interface RecapVerdict {
  experiment_id: string;
  verdict: string;
  effect_estimate: number | null;
  effect_ci_low: number | null;
  effect_ci_high: number | null;
  measured_at: string;
}

export interface ReceiptClaim {
  id: string;
  text: string;
  status: "supported" | "unsupported" | "contradicted" | "unverified";
  span_ids: string[];
}

export interface ReceiptDebt {
  score: number;
  components: ReceiptDebtComponent[];
  explanation: string;
}

export interface ReceiptDebtComponent {
  id: string;
  weight: number;
  active: boolean;
  reason: string;
}

export interface ReceiptEvidenceRef {
  kind: string;
  span_id: string | null;
  label: string;
}

export interface ReceiptIntent {
  present: boolean;
  span_id: string | null;
  summary: string | null;
  limitation: string | null;
}

export interface ReceiptOutcomeSummary {
  label: string | null;
  tests_run: number | null;
  tests_passed: number | null;
  tests_failed: number | null;
  build_status: string | null;
  human_label: string | null;
  quality_score: number | null;
}

export interface ReceiptRequirement {
  id: string;
  text: string;
  status: "supported" | "unsupported" | "contradicted" | "unverified";
  span_id: string | null;
}

export interface ReceiptResponse {
  schema_version: string;
  builder_version: string;
  trace_id: string;
  status: "verified" | "failed" | "debt" | "unverified" | "unknown";
  intent: ReceiptIntent;
  requirements: ReceiptRequirement[];
  claims: ReceiptClaim[];
  claims_limitation: string;
  evidence: ReceiptEvidenceRef[];
  timeline: ReceiptTimelineEvent[];
  debt: ReceiptDebt;
  outcome: ReceiptOutcomeSummary;
  risk_policy: ReceiptRiskPolicy;
  limitations: string[];
  content_hash: string;
  markdown: string | null;
  persisted: boolean;
}

export interface ReceiptRiskFinding {
  rule_id: string;
  risk: string;
  message: string;
  enforcement_source: "observed_violation" | "advisory_warning" | "allowlisted_exception";
  evidence: Record<string, unknown>;
}

export interface ReceiptRiskPolicy {
  evaluated: boolean;
  review_risk: "none" | "low" | "medium" | "high";
  findings: ReceiptRiskFinding[];
  limitation: string;
  enforcement_note: string | null;
}

export interface ReceiptTimelineEvent {
  kind: string;
  at: string;
  span_id: string | null;
  summary: string;
}

export interface RegionAggregate {
  region: string;
  tokens: number;
  spans: number;
  cost: number;
}

export interface RegionTrendPoint {
  day: string;
  region: string;
  tokens: number;
  cost: number;
}

export interface RegionsAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: ContextLedgerSummary;
  regions: RegionAggregate[];
  trend: RegionTrendPoint[];
  rebilled_blocks: RebilledBlock[];
  cache_trend: CacheTrendPoint[];
  agents: ContextAgentAggregate[];
  coverage: ContextCoverage[];
  schema_overhead_tokens: number;
  schema_overhead_cost: number;
  limitations: string[];
}

export interface ReplayCheckpoint {
  seq: number;
  spans: Span[];
  summary: ReplaySummary;
}

export interface ReplayResponse {
  trace_id: string;
  seq: number | null;
  max_seq: number | null;
  step: number | null;
  spans: Span[] | null;
  summary: ReplaySummary | null;
  checkpoints: ReplayCheckpoint[] | null;
}

export interface ReplaySummary {
  turn: number;
  context_tokens: number | null;
  cost: number;
  cost_estimated: boolean;
  files_read: number;
  agents: number;
}

export interface ResolvedTimeRange {
  start: string;
  end: string;
  prior_start: string;
  prior_end: string;
  timezone: string;
  preset: "24h" | "7d" | "30d" | "90d" | null;
  legacy_days: number | null;
  semantics: "rolling_duration" | "custom_calendar";
  duration_days: number;
}

export interface ResourceBudgetStatus {
  status: "ok" | "warn" | "over" | "unknown";
  soft_budget_bytes: number | null;
  ratio: number | null;
  message: string;
}

export interface ResourceDiskInventory {
  cairn_dir: string;
  total_bytes: number;
  database_bytes: number | null;
  wal_bytes: number | null;
  exports_bytes: number | null;
  backups_bytes: number | null;
  regressions_bytes: number | null;
}

export interface ResourceForecast {
  window_days: number;
  traces_ingested: number;
  estimated_bytes_per_day: number;
  projected_total_in_30d: number | null;
  kind: string;
  limitation: string;
}

export interface ResourceStatus {
  disk: ResourceDiskInventory;
  budget: ResourceBudgetStatus;
  forecast: ResourceForecast;
  process_rss_bytes: number | null;
  collection_mode: "manual" | "efficient" | "live" | null;
  limitation: string;
}

export interface SearchFacet {
  value: string;
  count: number;
}

export interface SearchHit {
  trace_id: string;
  span_id: string | null;
  title: string | null;
  snippet: string;
  kind: "trace" | "span";
}

export interface SearchResponse {
  q: string;
  filter_phrase: string;
  hits: SearchHit[];
  total: number;
  limit: number;
  offset: number;
  filter_tokens: QueryFilterToken[];
  filter_errors: QueryFilterError[];
  search_mode: "fts" | "scan";
  search_limitation: string | null;
  facets: Record<string, SearchFacet[]>;
}

export interface SessionShield {
  shield: "verification" | "scope" | "privacy" | "resource";
  state: "healthy" | "degraded" | "paused" | "quarantined" | "attention" | "unknown" | "unavailable";
  summary: string;
  facts: string[];
  limitation: string;
  action_label: string;
  action_path: string;
}

export interface ShieldSummary {
  shield: "verification" | "scope" | "privacy" | "resource";
  state: "healthy" | "degraded" | "paused" | "quarantined" | "attention" | "unknown" | "unavailable";
  summary: string;
  facts: string[];
  limitation: string;
  action_label: string;
  action_path: string;
}

export interface Span {
  span_id: string;
  trace_id: string;
  parent_span_id: string | null;
  seq: number;
  kind: "agent" | "llm_call" | "tool_call" | "tool_result" | "user_msg" | "assistant_msg" | "retrieval" | "subagent" | "compaction" | "system";
  name: string | null;
  agent_id: string | null;
  agent_lane: string | null;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  status: "ok" | "error" | "cancelled";
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  input_estimated: number;
  output_estimated: number;
  cache_read_tokens: number | null;
  cache_creation_tokens: number | null;
  context_tokens_after: number | null;
  text_inline: string | null;
  text_hash: string | null;
  args_hash: string | null;
  path_rel: string | null;
  waste_category: string | null;
  waste_tokens: number;
  attrs_json: Record<string, unknown>;
}

export interface SpanLink {
  from_span_id: string;
  to_span_id: string;
  link_type: string;
}

export interface SpanNode {
  span: Span;
  children: SpanNode[];
}

export interface TailAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  tail_risk: TailRisk;
  exceedances: number[];
}

export interface TailRisk {
  expected_worst_cost: number | null;
  exceedance_count: number;
  threshold: number | null;
}

export interface ToolAggregate {
  tool_id: string;
  display_name: string;
  family: string;
  invocations: number;
  sessions: number;
  success_count: number;
  error_count: number;
  cancelled_count: number;
  success_rate: number;
  error_rate: number;
  retry_rate: number;
  median_latency_ms: number | null;
  p95_latency_ms: number | null;
  result_tokens: number;
  estimated_cost_share: number;
  estimate_kind: string;
  trend: ToolTrendPoint[];
  worst_session: ToolEvidence | null;
  limitation: string;
}

export interface ToolCoverage {
  source: string;
  sessions: number;
  tool_sessions: number;
  tool_coverage_pct: number;
  distinct_tools: number;
  mapped_tools: number;
  limitation: string;
}

export interface ToolEvidence {
  trace_id: string;
  span_id: string;
  label: string;
}

export interface ToolFailureSample {
  tool_id: string;
  display_name: string;
  status: string;
  duration_ms: number | null;
  evidence: ToolEvidence;
  detail: string;
}

export interface ToolTrendPoint {
  day: string;
  invocations: number;
  errors: number;
}

export interface ToolsAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  ledger: ToolsLedgerSummary;
  tools: ToolAggregate[];
  failures: ToolFailureSample[];
  coverage: ToolCoverage[];
  schema_overhead_tokens: number;
  limitations: string[];
}

export interface ToolsLedgerSummary {
  conclusion: string;
  invocations: number;
  distinct_tools: number;
  sessions_with_tools: number;
  sessions_total: number;
  error_rate: number;
  retry_rate: number;
  schema_overhead_tokens: number;
  schema_tax_estimated: boolean;
  next_action: string;
  next_action_href: string | null;
  limitation: string;
}

export interface Trace {
  trace_id: string;
  workspace_id: string;
  source: string;
  external_id: string | null;
  actor_id: string | null;
  project: string | null;
  cwd: string | null;
  model: string | null;
  git_branch: string | null;
  git_commit: string | null;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  title: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  reasoning_tokens: number;
  cost: number;
  cost_source: string;
  context_window: number | null;
  peak_context_pct: number | null;
  span_count: number;
  tool_calls: number;
  tool_errors: number;
  waste_tokens: number;
  difficulty: number | null;
  difficulty_bucket: string | null;
}

export interface TraceDetailResponse {
  trace: Trace;
  spans: Span[];
  tree: SpanNode[];
  links: SpanLink[];
  mcp_consultations: McpConsultation[];
  regions: ContextRegion[];
  diagnostics: Diagnostic | null;
  quality: DataQuality | null;
  outcome: Outcome | null;
  shields: SessionShield[];
  postmortem: PostmortemResponse | null;
  receipt: ReceiptResponse | null;
  corrections: CorrectionsResponse | null;
  handoff: HandoffResponse | null;
}

export interface TraceDiffAnalysis {
  tokens_a: number;
  tokens_b: number;
  delta_tokens: number;
  duration_ms_a: number | null;
  duration_ms_b: number | null;
  delta_duration_ms: number | null;
  models_a: string[];
  models_b: string[];
  regions: TraceDiffRegion[];
  outcome_a: Outcome | null;
  outcome_b: Outcome | null;
  diagnostic_a: Diagnostic | null;
  diagnostic_b: Diagnostic | null;
  alignment_mode: "lcs" | "bounded_position";
  alignment_truncated: boolean;
  alignment_limitation: string | null;
  comparability: TraceDiffComparability;
  what_changed: TraceDiffChange[];
  evidence: TraceDiffEvidence[];
}

export interface TraceDiffChange {
  statement: string;
  basis: "recorded_delta" | "diagnostic" | "limitation";
  evidence: TraceDiffEvidence[];
}

export interface TraceDiffComparability {
  state: "comparable" | "limited" | "not_comparable";
  reasons: string[];
  facts: string[];
  limitation: string;
}

export interface TraceDiffEvidence {
  side: "a" | "b" | "both";
  label: string;
  trace_id: string;
  span_id: string | null;
  evidence_type: "session" | "span" | "diagnostic" | "outcome" | "region";
}

export interface TraceDiffRegion {
  region: string;
  tokens_a: number;
  tokens_b: number;
  delta_tokens: number;
  cost_a: number;
  cost_b: number;
  delta_cost: number;
}

export interface TraceDiffResponse {
  a: Trace;
  b: Trace;
  summary: TraceDiffSummary;
  turns: TraceDiffTurn[];
  analysis: TraceDiffAnalysis;
}

export interface TraceDiffSummary {
  cost_a: number;
  cost_b: number;
  delta_cost: number;
  waste_a: number;
  waste_b: number;
  delta_waste_tokens: number;
  quality_a: number;
  quality_b: number;
  delta_quality: number;
}

export interface TraceDiffTurn {
  index: number;
  op: "match" | "insert" | "delete";
  a: Span | null;
  b: Span | null;
  delta_tokens: number;
  delta_waste_tokens: number;
  delta_quality: number;
}

export interface TraceRow {
  trace_id: string;
  source: string;
  title: string | null;
  project: string | null;
  actor_id: string | null;
  model: string | null;
  started_at: string | null;
  ended_at: string | null;
  status: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  cost_source: string;
  span_count: number;
  waste_tokens: number;
  difficulty: number | null;
  duration_ms: number | null;
  token_flow: number[];
  quality_score: number | null;
  outcome_label: string | null;
  verification_state: "verified" | "failed" | "debt" | "unverified" | "unknown";
  first_user_request: string | null;
  top_files: string[];
  data_quality_state: "measured" | "partial" | "degraded" | "unavailable";
}

export interface TracesListResponse {
  traces: TraceRow[];
  total: number;
  limit: number;
  offset: number;
  resolved_range: ResolvedTimeRange | null;
  filter_phrase: string;
  filter_tokens: QueryFilterToken[];
  filter_errors: QueryFilterError[];
}

export interface TrendAnnotation {
  occurred_at: string;
  label: string;
  kind: "experiment" | "guard";
  action_path: string;
}

export interface UsageAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  group_by: string;
  series: UsageSeriesPoint[];
}

export interface UsageSeriesPoint {
  key: string;
  input_tokens: number;
  output_tokens: number;
  waste_tokens: number;
  cost: number;
  traces: number;
}

export interface VerdictHistoryEntry {
  at: string;
  verdict: string | null;
  plain_verdict: string | null;
  effect_estimate: number | null;
  effect_ci_low: number | null;
  effect_ci_high: number | null;
  sample_size: number | null;
  outcome_n_raw: number | null;
  decay_state: "healthy" | "decaying" | "decayed" | "unknown" | null;
  regression_outside_interval: boolean;
}

export interface VerdictPreviewData {
  expected_days_to_verdict: number | null;
  traces_per_day: number;
  n_effective_needed: number;
  traffic_unknown: boolean;
}

export interface WasteAnalyticsResponse {
  days: number;
  resolved_range: ResolvedTimeRange;
  categories: WasteCategory[];
  total_waste_tokens: number;
}

export interface WasteCategory {
  category: string;
  tokens: number;
  events: number;
}

export interface WasteCause {
  category: string;
  waste_tokens: number;
  estimated_savings_usd: number;
  cause: string;
  fix: string;
  confidence: "low" | "medium";
  confidence_explanation: string;
  evidence_count: number;
  evidence: OverviewEvidence[];
}

export interface WorkspaceAdapter {
  source: string;
  streams: number;
  cursor_updated_at: string | null;
  attempts: number;
  fully_parsed: number;
  degraded: number;
  skipped: number;
  parse_coverage: number | null;
  unknown_fields: Record<string, number>;
  last_success_at: string | null;
  warning: boolean;
  issue_url: string;
}

export interface WorkspaceHealth {
  trace_count: number;
  insight_count: number;
  fts_available: boolean;
  adapter_warnings: AdapterWarning[];
  human_label_agreement: HumanLabelAgreement;
}

export interface WorkspaceResponse {
  workspace_id: string;
  root_path: string;
  name: string;
  adapters: WorkspaceAdapter[];
  health: WorkspaceHealth;
  gauge: PlanWindowGauge | null;
  collection: CollectionStatus | null;
  resources: ResourceStatus | null;
}
