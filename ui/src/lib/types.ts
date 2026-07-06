/** API types aligned with server/api/schemas.py */

export type TimeRange = "24h" | "7d" | "30d" | "90d";

export type SpanKind =
  | "agent"
  | "llm_call"
  | "tool_call"
  | "tool_result"
  | "user_msg"
  | "assistant_msg"
  | "retrieval"
  | "subagent"
  | "compaction"
  | "system";

export type InsightSeverity = "info" | "suggestion" | "warning" | "error";
export type InsightLifecycle = "new" | "ack" | "fixed" | "regressed" | "muted";

export interface DataNote {
  source: string;
  sessions: number;
  issue: string;
  message: string;
  help_url?: string | null;
}

export interface NarrativeSentence {
  text: string;
  filter?: Record<string, string> | null;
}

export interface TailRisk {
  expected_worst_cost?: number | null;
  exceedance_count: number;
  threshold?: number | null;
}

export interface OverviewResponse {
  days: number;
  kpis: Record<string, number | null>;
  narrative: NarrativeSentence[];
  tail_risk: TailRisk;
  data_notes: DataNote[];
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
}

export interface TracesListResponse {
  traces: TraceRow[];
  total: number;
  limit: number;
  offset: number;
}

export interface Span {
  span_id: string;
  trace_id: string;
  parent_span_id: string | null;
  seq: number;
  kind: SpanKind;
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
  path_rel: string | null;
  waste_category: string | null;
  waste_tokens: number;
}

export interface SpanNode {
  span: Span;
  children: SpanNode[];
}

export interface Trace {
  trace_id: string;
  workspace_id: string;
  source: string;
  title: string | null;
  project: string | null;
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
  peak_context_pct: number | null;
}

export interface TraceDetailResponse {
  trace: Trace;
  spans: Span[];
  tree: SpanNode[];
  links: { from_span_id: string; to_span_id: string; link_type: string }[];
  regions: Record<string, unknown>[];
  diagnostics: Record<string, unknown> | null;
  quality: Record<string, unknown> | null;
}

export interface ReplayCheckpoint {
  seq: number;
  spans: Span[];
  summary: Record<string, unknown>;
}

export interface ReplayResponse {
  trace_id: string;
  seq?: number | null;
  max_seq?: number | null;
  step?: number | null;
  spans?: Span[] | null;
  summary?: Record<string, unknown> | null;
  checkpoints?: ReplayCheckpoint[] | null;
}

export interface InsightRow {
  insight_id: string;
  fingerprint: string;
  detector: string;
  severity: InsightSeverity;
  title: string;
  body: string;
  state: InsightLifecycle;
  savings_estimate: number | null;
  action: string | null;
  last_seen_at: string;
}

export interface InsightsResponse {
  insights: InsightRow[];
  total: number;
}

export interface EvidenceChainResponse {
  insight_id: string;
  evidence_id: string;
  producer: string;
  produced_at: string;
  trace_ids: string[];
  span_ids: string[] | null;
  metrics: Record<string, unknown>;
  spans: Span[];
}

export interface ActionManifestEntry {
  name: string;
  title: string;
  category: string;
  params_schema: Record<string, unknown>;
  async_job: boolean;
}

export interface ActionsManifestResponse {
  actions: ActionManifestEntry[];
}

export interface AgentAggregate {
  agent_id: string | null;
  actor_id: string | null;
  traces: number;
  input_tokens: number;
  output_tokens: number;
  cost: number;
}

export interface AgentsResponse {
  days: number;
  agents: AgentAggregate[];
  handoff_matrix: Record<string, unknown>[];
}

export interface BehaviorResponse {
  days: number;
  series: Record<string, unknown>[];
  drift: Record<string, unknown>[];
  radar: Record<string, unknown> | null;
  data_notes: DataNote[];
}

export interface QualityResponse {
  days: number;
  outcomes: Record<string, unknown>[];
  histogram: { bucket: string; count: number }[];
  cost_per_success: Record<string, unknown>[];
  data_notes: DataNote[];
}

export interface RegionsAnalyticsResponse {
  days: number;
  regions: { region: string; tokens: number; spans: number }[];
}

export interface WasteAnalyticsResponse {
  days: number;
  categories: { category: string; tokens: number; events: number }[];
  total_waste_tokens: number;
}

export interface UsageSeriesRow {
  key: string;
  input_tokens: number;
  output_tokens: number;
  cost: number;
  traces: number;
}

export interface UsageAnalyticsResponse {
  days: number;
  group_by: string;
  series: UsageSeriesRow[];
}

export interface TailAnalyticsResponse {
  days: number;
  tail_risk: TailRisk;
  exceedances: number[];
}

export interface ExperimentRow {
  experiment_id: string;
  status: string;
  target_file: string | null;
  created_at: string;
  verdict: string | null;
  lift_pct: number | null;
}

export interface ExperimentsResponse {
  experiments: ExperimentRow[];
}

export interface ExperimentDetailResponse {
  experiment: Record<string, unknown>;
  preview?: VerdictPreviewData | null;
}

export interface VerdictPreviewData {
  expected_days_to_verdict: number | null;
  traces_per_day: number;
  n_effective_needed: number;
  traffic_unknown: boolean;
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
  hits: SearchHit[];
  total: number;
}

export interface WorkspaceAdapter {
  source: string;
  streams: number;
  cursor_updated_at: string | null;
}

export interface PlanWindowGauge {
  window_hours: number;
  total_tokens: number;
  by_source: Record<string, number>;
  limit: number | null;
  exceeded: boolean;
}

export interface WorkspaceResponse {
  workspace_id: string;
  root_path: string;
  name: string;
  adapters: WorkspaceAdapter[];
  health: Record<string, unknown>;
  gauge?: PlanWindowGauge | null;
}
