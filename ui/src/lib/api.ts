import type {
  ActionsManifestResponse,
  AgentsResponse,
  BehaviorResponse,
  EvidenceChainResponse,
  ExperimentDetailResponse,
  ExperimentsResponse,
  InsightsResponse,
  OverviewResponse,
  RecapResponse,
  QualityResponse,
  ReceiptResponse,
  RegionsAnalyticsResponse,
  BudgetBurnResponse,
  CompareAnalyticsResponse,
  GuardAnalyticsResponse,
  FilesAnalyticsResponse,
  ToolsAnalyticsResponse,
  ReplayResponse,
  SearchResponse,
  TailAnalyticsResponse,
  TraceDetailResponse,
  TraceDiffResponse,
  TracesListResponse,
  UsageAnalyticsResponse,
  WasteAnalyticsResponse,
  WorkspaceResponse,
} from "./generated/api-types";
import type * as View from "./types";
import type { TimeRangeRequest } from "./types";
import { timeRangeParams } from "./timeRange";

const API_BASE = "/api";
const STATIC_API_BASE = "./api";
const STATIC_SLUG_RE = /[^A-Za-z0-9._-]+/g;

declare global {
  interface Window {
    __CAIRN_STATIC__?: boolean;
    __CAIRN_STATIC_DATA__?: Record<string, unknown>;
  }
}

function slug(value: string): string {
  const cleaned = value.replace(STATIC_SLUG_RE, "-").replace(/^-+|-+$/g, "");
  return cleaned || "x";
}

function staticQuerySuffix(rawQuery: string): string {
  if (!rawQuery) return "";
  const params = new URLSearchParams(rawQuery);
  const pairs = Array.from(params.entries())
    .filter(([, value]) => value.length > 0)
    .sort(([a], [b]) => a.localeCompare(b));
  if (pairs.length === 0) return "";
  return `__${pairs.map(([k, v]) => `${slug(k)}=${slug(v)}`).join("__")}`;
}

function staticJsonPath(path: string): string {
  const [rawPath, rawQuery = ""] = path.split("?");
  const rel = (rawPath ?? "").replace(/^\/+/, "") || "root";
  return `${STATIC_API_BASE}/${rel}${staticQuerySuffix(rawQuery)}.json`;
}

export function isStaticMode(): boolean {
  return Boolean(window.__CAIRN_STATIC__);
}

export interface HealthResponse {
  status: string;
  version: string;
}

export interface StaticManifest {
  schema_version: number;
  producer_version: string;
  captured_at: string;
  data_bounds: { start: string | null; end: string | null; timezone: string };
  available_days: number[];
  supported_queries: Record<string, unknown>;
  custom_range_behavior: "rejected";
  mutations: false;
  live_updates: false;
  privacy: "scrubbed";
  unsupported: string[];
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed: ${res.status}`);
  return res.json() as Promise<HealthResponse>;
}

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  if (isStaticMode() && method !== "GET") {
    throw new Error("This is a read-only static snapshot.");
  }
  const url = isStaticMode() ? staticJsonPath(path) : `${API_BASE}${path}`;
  if (isStaticMode()) {
    const payloads = window.__CAIRN_STATIC_DATA__;
    if (!payloads || !Object.prototype.hasOwnProperty.call(payloads, url)) {
      throw new Error(
        "This static snapshot does not include that view, filter, or page. " +
          "Use a captured preset or open the live local app.",
      );
    }
    return payloads[url] as T;
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message =
      typeof body === "object" && body !== null && "error" in body
        ? String((body as { error: { message?: string } }).error.message ?? res.statusText)
        : res.statusText;
    throw new Error(message);
  }
  return res.json() as Promise<T>;
}

export function fetchStaticManifest(): Promise<StaticManifest> {
  return fetchJson("/static-manifest");
}

export { timeRangeDays } from "./timeRange";

function rangeQuery(range: TimeRangeRequest | number): string {
  return timeRangeParams(range, isStaticMode()).toString();
}

export function fetchOverview(range: TimeRangeRequest | number): Promise<OverviewResponse> {
  return fetchJson(`/overview?${rangeQuery(range)}`);
}

export function fetchRecap(): Promise<RecapResponse> {
  return fetchJson("/recap");
}

export function fetchTraces(params: {
  days?: number;
  range?: TimeRangeRequest;
  source?: string;
  agent?: string;
  q?: string;
  sort?: "recent" | "waste" | "cost" | "duration" | "tokens" | "quality";
  limit?: number;
  offset?: number;
}): Promise<TracesListResponse> {
  const qs = new URLSearchParams();
  const rangeParams = params.range
    ? timeRangeParams(params.range, isStaticMode())
    : params.days
      ? timeRangeParams(params.days)
      : new URLSearchParams();
  rangeParams.forEach((value, key) => qs.set(key, value));
  if (params.source) qs.set("source", params.source);
  if (params.agent) qs.set("agent", params.agent);
  if (params.q) qs.set("q", params.q);
  if (params.sort && params.sort !== "recent") qs.set("sort", params.sort);
  qs.set("limit", String(params.limit ?? 50));
  qs.set("offset", String(params.offset ?? 0));
  return fetchJson(`/traces?${qs}`);
}

export async function fetchTraceDetail(traceId: string): Promise<View.TraceDetailResponse> {
  const transport = await fetchJson<TraceDetailResponse>(`/traces/${encodeURIComponent(traceId)}`);
  return transport as unknown as View.TraceDetailResponse;
}

export async function fetchTraceReceipt(traceId: string): Promise<View.ReceiptResponse> {
  const transport = await fetchJson<ReceiptResponse>(
    `/traces/${encodeURIComponent(traceId)}/receipt`,
  );
  return transport as unknown as View.ReceiptResponse;
}

export function setHumanLabel(
  traceId: string,
  label: "up" | "down" | null,
  note?: string,
): Promise<{ trace_id: string; label: "up" | "down" | null; note: string | null }> {
  return fetchJson(`/traces/${encodeURIComponent(traceId)}/human-label`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ label, note: note || null }),
  });
}

export async function fetchReplayCheckpoints(traceId: string): Promise<View.ReplayResponse> {
  const transport = await fetchJson<ReplayResponse>(
    `/traces/${encodeURIComponent(traceId)}/replay`,
  );
  return transport as unknown as View.ReplayResponse;
}

export async function fetchReplay(traceId: string, seq: number): Promise<View.ReplayResponse> {
  const transport = await fetchJson<ReplayResponse>(
    `/traces/${encodeURIComponent(traceId)}/replay?seq=${seq}`,
  );
  return transport as unknown as View.ReplayResponse;
}

export async function fetchTraceDiff(
  traceIdA: string,
  traceIdB: string,
): Promise<View.TraceDiffResponse> {
  const qs = new URLSearchParams({ a: traceIdA, b: traceIdB });
  const transport = await fetchJson<TraceDiffResponse>(`/traces/diff?${qs}`);
  return transport as unknown as View.TraceDiffResponse;
}

export function fetchInsights(state?: string): Promise<InsightsResponse> {
  const qs = state ? `?state=${encodeURIComponent(state)}` : "";
  return fetchJson(`/insights${qs}`);
}

export function fetchInsightEvidence(insightId: string): Promise<EvidenceChainResponse> {
  return fetchJson(`/insights/${encodeURIComponent(insightId)}/evidence`);
}

export function fetchActions(): Promise<ActionsManifestResponse> {
  return fetchJson("/actions");
}

export function runAction(
  name: string,
  params: Record<string, unknown> = {},
): Promise<{
  ok: boolean;
  result?: Record<string, unknown>;
  job_id?: string;
}> {
  if (isStaticMode()) {
    return Promise.reject(new Error("Actions are disabled in static mode."));
  }
  return fetchJson(`/actions/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export type ActionJobStatus = {
  job_id: string;
  action: string;
  status: string;
  progress: number;
  message: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  created_at: string;
  finished_at: string | null;
};

export function fetchActionJob(jobId: string): Promise<ActionJobStatus> {
  return fetchJson(`/actions/jobs/${encodeURIComponent(jobId)}`);
}

/** Poll an async action job until it finishes (or times out). */
export async function waitForActionJob(
  jobId: string,
  {
    intervalMs = 750,
    timeoutMs = 10 * 60 * 1000,
    onProgress,
    signal,
  }: {
    intervalMs?: number;
    timeoutMs?: number;
    onProgress?: (job: ActionJobStatus) => void;
    signal?: AbortSignal;
  } = {},
): Promise<ActionJobStatus> {
  const started = Date.now();
  for (;;) {
    if (signal?.aborted) {
      throw new Error(`Aborted waiting for job ${jobId}`);
    }
    const job = await fetchActionJob(jobId);
    onProgress?.(job);
    if (
      job.status === "done" ||
      job.status === "error" ||
      job.status === "cancelled" ||
      job.status === "rejected"
    ) {
      return job;
    }
    if (Date.now() - started > timeoutMs) {
      throw new Error(`Timed out waiting for job ${jobId}`);
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
}

export function fetchAgents(range: TimeRangeRequest | number): Promise<AgentsResponse> {
  return fetchJson(`/agents?${rangeQuery(range)}`);
}

export function fetchBehavior(range: TimeRangeRequest | number): Promise<BehaviorResponse> {
  return fetchJson(`/behavior?${rangeQuery(range)}`);
}

export function fetchQuality(range: TimeRangeRequest | number): Promise<QualityResponse> {
  return fetchJson(`/quality?${rangeQuery(range)}`);
}

export function fetchRegions(range: TimeRangeRequest | number): Promise<RegionsAnalyticsResponse> {
  return fetchJson(`/analytics/regions?${rangeQuery(range)}`);
}

export function fetchTools(range: TimeRangeRequest | number): Promise<ToolsAnalyticsResponse> {
  return fetchJson(`/analytics/tools?${rangeQuery(range)}`);
}

export function fetchFiles(range: TimeRangeRequest | number): Promise<FilesAnalyticsResponse> {
  return fetchJson(`/analytics/files?${rangeQuery(range)}`);
}

export function fetchCompare(range: TimeRangeRequest | number): Promise<CompareAnalyticsResponse> {
  return fetchJson(`/analytics/compare?${rangeQuery(range)}`);
}

export function fetchGuard(range: TimeRangeRequest | number): Promise<GuardAnalyticsResponse> {
  return fetchJson(`/analytics/guard?${rangeQuery(range)}`);
}

export function fetchBudget(range?: TimeRangeRequest | number): Promise<BudgetBurnResponse> {
  const query = range == null ? "days=30" : rangeQuery(range);
  return fetchJson(`/analytics/budget?${query}`);
}

export function fetchWaste(range: TimeRangeRequest | number): Promise<WasteAnalyticsResponse> {
  return fetchJson(`/analytics/waste?${rangeQuery(range)}`);
}

export function fetchUsage(range: TimeRangeRequest | number): Promise<UsageAnalyticsResponse> {
  return fetchJson(`/analytics/usage?${rangeQuery(range)}&group_by=day`);
}

export function fetchTail(range: TimeRangeRequest | number): Promise<TailAnalyticsResponse> {
  return fetchJson(`/analytics/tail?${rangeQuery(range)}`);
}

export function fetchExperimentDetail(experimentId: string): Promise<ExperimentDetailResponse> {
  return fetchJson(`/experiments/${encodeURIComponent(experimentId)}`);
}

export function fetchExperiments(): Promise<ExperimentsResponse> {
  return fetchJson("/experiments");
}

export function fetchSearch(q: string, limit = 20, offset = 0): Promise<SearchResponse> {
  const qs = new URLSearchParams({ q, limit: String(limit) });
  if (offset > 0) qs.set("offset", String(offset));
  return fetchJson(`/search?${qs}`);
}

export function fetchWorkspace(): Promise<WorkspaceResponse> {
  return fetchJson("/workspace");
}
