import type {
  ActionsManifestResponse,
  AgentsResponse,
  BehaviorResponse,
  EvidenceChainResponse,
  ExperimentDetailResponse,
  ExperimentsResponse,
  InsightsResponse,
  OverviewResponse,
  QualityResponse,
  RegionsAnalyticsResponse,
  ReplayResponse,
  SearchResponse,
  TailAnalyticsResponse,
  TraceDetailResponse,
  TraceDiffResponse,
  TracesListResponse,
  UsageAnalyticsResponse,
  WasteAnalyticsResponse,
  WorkspaceResponse,
} from "./types";

const API_BASE = "/api";
const STATIC_API_BASE = "./api";
const STATIC_SLUG_RE = /[^A-Za-z0-9._-]+/g;

declare global {
  interface Window {
    __CAIRN_STATIC__?: boolean;
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

export function timeRangeDays(range: string): number {
  switch (range) {
    case "24h":
      return 1;
    case "7d":
      return 7;
    case "30d":
      return 30;
    case "90d":
      return 90;
    default:
      return 30;
  }
}

export function fetchOverview(days: number): Promise<OverviewResponse> {
  return fetchJson(`/overview?days=${days}`);
}

export function fetchTraces(params: {
  days?: number;
  source?: string;
  agent?: string;
  q?: string;
  sort?: "recent" | "waste" | "cost";
  limit?: number;
  offset?: number;
}): Promise<TracesListResponse> {
  const qs = new URLSearchParams();
  if (params.days) qs.set("days", String(params.days));
  if (params.source) qs.set("source", params.source);
  if (params.agent) qs.set("agent", params.agent);
  if (params.q) qs.set("q", params.q);
  if (params.sort && params.sort !== "recent") qs.set("sort", params.sort);
  qs.set("limit", String(params.limit ?? 50));
  qs.set("offset", String(params.offset ?? 0));
  return fetchJson(`/traces?${qs}`);
}

export function fetchTraceDetail(traceId: string): Promise<TraceDetailResponse> {
  return fetchJson(`/traces/${encodeURIComponent(traceId)}`);
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

export function fetchReplayCheckpoints(traceId: string): Promise<ReplayResponse> {
  return fetchJson(`/traces/${encodeURIComponent(traceId)}/replay`);
}

export function fetchReplay(traceId: string, seq: number): Promise<ReplayResponse> {
  return fetchJson(`/traces/${encodeURIComponent(traceId)}/replay?seq=${seq}`);
}

export function fetchTraceDiff(traceIdA: string, traceIdB: string): Promise<TraceDiffResponse> {
  const qs = new URLSearchParams({ a: traceIdA, b: traceIdB });
  return fetchJson(`/traces/diff?${qs}`);
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

export function runAction(name: string, params: Record<string, unknown> = {}): Promise<{
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

export function fetchAgents(days: number): Promise<AgentsResponse> {
  return fetchJson(`/agents?days=${days}`);
}

export function fetchBehavior(days: number): Promise<BehaviorResponse> {
  return fetchJson(`/behavior?days=${days}`);
}

export function fetchQuality(days: number): Promise<QualityResponse> {
  return fetchJson(`/quality?days=${days}`);
}

export function fetchRegions(days: number): Promise<RegionsAnalyticsResponse> {
  return fetchJson(`/analytics/regions?days=${days}`);
}

export function fetchWaste(days: number): Promise<WasteAnalyticsResponse> {
  return fetchJson(`/analytics/waste?days=${days}`);
}

export function fetchUsage(days: number): Promise<UsageAnalyticsResponse> {
  return fetchJson(`/analytics/usage?days=${days}&group_by=day`);
}

export function fetchTail(days: number): Promise<TailAnalyticsResponse> {
  return fetchJson(`/analytics/tail?days=${days}`);
}

export function fetchExperimentDetail(experimentId: string): Promise<ExperimentDetailResponse> {
  return fetchJson(`/experiments/${encodeURIComponent(experimentId)}`);
}

export function fetchExperiments(): Promise<ExperimentsResponse> {
  return fetchJson("/experiments");
}

export function fetchSearch(q: string, limit = 20): Promise<SearchResponse> {
  const qs = new URLSearchParams({ q, limit: String(limit) });
  return fetchJson(`/search?${qs}`);
}

export function fetchWorkspace(): Promise<WorkspaceResponse> {
  return fetchJson("/workspace");
}
