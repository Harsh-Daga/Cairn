import type {
  ActionsManifestResponse,
  EvidenceChainResponse,
  InsightsResponse,
  OverviewResponse,
  ReplayResponse,
  TraceDetailResponse,
  TracesListResponse,
} from "./types";

const API_BASE = "/api";

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
  const res = await fetch(`${API_BASE}${path}`, init);
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
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<TracesListResponse> {
  const qs = new URLSearchParams();
  if (params.days) qs.set("days", String(params.days));
  if (params.source) qs.set("source", params.source);
  if (params.q) qs.set("q", params.q);
  qs.set("limit", String(params.limit ?? 50));
  qs.set("offset", String(params.offset ?? 0));
  return fetchJson(`/traces?${qs}`);
}

export function fetchTraceDetail(traceId: string): Promise<TraceDetailResponse> {
  return fetchJson(`/traces/${encodeURIComponent(traceId)}`);
}

export function fetchReplay(traceId: string, seq: number): Promise<ReplayResponse> {
  return fetchJson(`/traces/${encodeURIComponent(traceId)}/replay?seq=${seq}`);
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
  return fetchJson(`/actions/${encodeURIComponent(name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}
