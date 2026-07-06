import { describe, expect, it } from "vitest";
import {
  formatZoomParam,
  parseZoomParam,
  timeBarLayout,
  tokenBarLayout,
  traceDurationMs,
  zoomDomainForSpan,
} from "@/lib/waterfallLayout";
import type { Span } from "@/lib/types";

function span(partial: Partial<Span> & Pick<Span, "span_id">): Span {
  return {
    trace_id: "t1",
    parent_span_id: null,
    seq: 1,
    kind: "tool_call",
    name: "read",
    agent_id: null,
    agent_lane: null,
    started_at: null,
    ended_at: null,
    duration_ms: 1000,
    status: "ok",
    model: null,
    input_tokens: 100,
    output_tokens: 50,
    input_estimated: 0,
    output_estimated: 0,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    context_tokens_after: null,
    text_inline: null,
    path_rel: null,
    waste_category: null,
    waste_tokens: 0,
    ...partial,
  };
}

describe("waterfallLayout", () => {
  it("computes token bar width from span tokens", () => {
    const layout = tokenBarLayout(span({ span_id: "a", input_tokens: 500, output_tokens: 0 }), 1000);
    expect(layout.widthPct).toBe(50);
    expect(layout.hatched).toBe(false);
  });

  it("positions time bars by offset and duration", () => {
    const traceStart = Date.parse("2026-01-01T00:00:00.000Z");
    const layout = timeBarLayout(
      span({
        span_id: "a",
        started_at: "2026-01-01T00:00:10.000Z",
        duration_ms: 5000,
      }),
      traceStart,
      60_000,
    );
    expect(layout.leftPct).toBeCloseTo(16.666, 1);
    expect(layout.widthPct).toBeGreaterThan(0);
    expect(layout.hatched).toBe(false);
  });

  it("marks missing timestamps as hatched full row", () => {
    const layout = timeBarLayout(span({ span_id: "a", started_at: null }), 0, 1000);
    expect(layout.hatched).toBe(true);
    expect(layout.widthPct).toBe(100);
  });

  it("round-trips zoom URL param", () => {
    const domain = { startMs: 1000, endMs: 9000 };
    expect(parseZoomParam(formatZoomParam(domain))).toEqual(domain);
  });

  it("builds zoom domain around a span", () => {
    const traceStart = Date.parse("2026-01-01T00:00:00.000Z");
    const domain = zoomDomainForSpan(
      span({
        span_id: "a",
        started_at: "2026-01-01T00:00:20.000Z",
        duration_ms: 10_000,
      }),
      traceStart,
      120_000,
    );
    expect(domain).not.toBeNull();
    expect(domain!.startMs).toBeGreaterThanOrEqual(traceStart);
  });

  it("derives trace duration from span timestamps", () => {
    const duration = traceDurationMs(
      "2026-01-01T00:00:00.000Z",
      null,
      [
        span({
          span_id: "a",
          started_at: "2026-01-01T00:00:00.000Z",
          duration_ms: 5000,
        }),
        span({
          span_id: "b",
          started_at: "2026-01-01T00:00:30.000Z",
          duration_ms: 10_000,
        }),
      ],
    );
    expect(duration).toBe(40_000);
  });
});
