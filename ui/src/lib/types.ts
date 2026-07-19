/**
 * Public UI type entry point.
 *
 * HTTP transport models are generated from FastAPI OpenAPI. The aliases below are UI vocabulary
 * or compatibility names only; do not duplicate response interfaces here.
 */
export * from "./generated/api-types";

import type { InsightRow, Outcome, Span, UsageSeriesPoint } from "./generated/api-types";

export type TimeRange = "24h" | "7d" | "30d" | "90d";
export interface CustomTimeRange {
  start: string;
  end: string;
  timezone: string;
}
export type TimeRangeRequest = TimeRange | CustomTimeRange;
export type SpanKind = Span["kind"];
export type InsightSeverity = InsightRow["severity"];
export type InsightLifecycle = InsightRow["state"];
export type UsageSeriesRow = UsageSeriesPoint;
export type OutcomeRecord = Outcome;
