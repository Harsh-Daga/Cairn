/** Placeholder types — generated from OpenAPI in scripts/build_ui.py (Phase 7). */

export interface TraceRow {
  trace_id: string;
  title: string | null;
  source: string;
  started_at: string | null;
  cost: number;
  input_tokens: number;
  output_tokens: number;
}

export interface InsightRow {
  insight_id: string;
  title: string;
  severity: string;
  state: string;
}

export type TimeRange = "24h" | "7d" | "30d" | "90d";
