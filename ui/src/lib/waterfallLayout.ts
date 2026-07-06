import type { Span } from "@/lib/types";

export type WaterfallMode = "tokens" | "time";

export interface TimeDomain {
  startMs: number;
  endMs: number;
}

export interface BarLayout {
  leftPct: number;
  widthPct: number;
  hatched: boolean;
}

const MIN_TIME_WIDTH_PCT = 0.5;

export function parseIsoMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

export function traceDurationMs(
  traceStartedAt: string | null | undefined,
  traceEndedAt: string | null | undefined,
  spans: Span[],
): number {
  const start = parseIsoMs(traceStartedAt);
  const end = parseIsoMs(traceEndedAt);
  if (start != null && end != null && end > start) {
    return end - start;
  }
  const spanEnd = spans.reduce((max, span) => {
    const at = parseIsoMs(span.started_at);
    const dur = span.duration_ms ?? 0;
    if (at == null) return max;
    return Math.max(max, at + dur);
  }, start ?? 0);
  if (start != null && spanEnd > start) {
    return spanEnd - start;
  }
  const maxDur = spans.reduce((m, span) => Math.max(m, span.duration_ms ?? 0), 0);
  return maxDur > 0 ? maxDur : 1;
}

export function tokenBarLayout(span: Span, tokenMax: number): BarLayout {
  const tokens = (span.input_tokens ?? 0) + (span.output_tokens ?? 0);
  const widthPct = Math.max(4, (tokens / Math.max(tokenMax, 1)) * 100);
  return { leftPct: 0, widthPct, hatched: false };
}

export function timeBarLayout(
  span: Span,
  traceStartMs: number,
  durationMs: number,
  domain?: TimeDomain | null,
): BarLayout {
  const domainStart = domain?.startMs ?? traceStartMs;
  const domainEnd = domain?.endMs ?? traceStartMs + durationMs;
  const domainDur = Math.max(domainEnd - domainStart, 1);

  const spanStart = parseIsoMs(span.started_at);
  if (spanStart == null) {
    return { leftPct: 0, widthPct: 100, hatched: true };
  }

  const offset = Math.max(0, spanStart - domainStart);
  const spanDur = Math.max(span.duration_ms ?? 0, 1);
  const leftPct = (offset / domainDur) * 100;
  const widthPct = Math.max((spanDur / domainDur) * 100, MIN_TIME_WIDTH_PCT);
  return { leftPct, widthPct, hatched: false };
}

export function zoomDomainForSpan(
  span: Span,
  traceStartMs: number,
  durationMs: number,
  paddingRatio = 0.1,
): TimeDomain | null {
  const spanStart = parseIsoMs(span.started_at);
  if (spanStart == null) return null;
  const spanDur = Math.max(span.duration_ms ?? 0, 1);
  const pad = spanDur * paddingRatio;
  const startMs = Math.max(traceStartMs, spanStart - pad);
  const endMs = Math.min(traceStartMs + durationMs, spanStart + spanDur + pad);
  if (endMs <= startMs) return null;
  return { startMs, endMs };
}

export function parseZoomParam(raw: string | null): TimeDomain | null {
  if (!raw) return null;
  const parts = raw.split(",");
  if (parts.length !== 2) return null;
  const start = Number(parts[0]);
  const end = Number(parts[1]);
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
    return null;
  }
  return { startMs: start, endMs: end };
}

export function formatZoomParam(domain: TimeDomain): string {
  return `${Math.round(domain.startMs)},${Math.round(domain.endMs)}`;
}

export function spansMissingTimestamps(spans: Span[]): boolean {
  return spans.some((span) => parseIsoMs(span.started_at) == null);
}

export function formatTimeRulerLabel(ms: number, originMs: number): string {
  const deltaSec = Math.max(0, Math.round((ms - originMs) / 1000));
  if (deltaSec < 60) return `${deltaSec}s`;
  const min = Math.floor(deltaSec / 60);
  const sec = deltaSec % 60;
  return sec > 0 ? `${min}m${sec}s` : `${min}m`;
}
