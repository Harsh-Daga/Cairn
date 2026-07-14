import { describe, expect, it } from "vitest";
import { mergeConsultationRows } from "@/lib/mcpConsultations";
import type { Span } from "@/lib/types";

function span(seq: number): Span {
  return {
    span_id: `span-${seq}`,
    trace_id: "trace-1",
    parent_span_id: null,
    seq,
    kind: "tool_call",
    name: "read",
    agent_id: null,
    agent_lane: null,
    started_at: null,
    ended_at: null,
    duration_ms: null,
    status: "ok",
    model: null,
    input_tokens: 0,
    output_tokens: 0,
    input_estimated: 0,
    output_estimated: 0,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    context_tokens_after: null,
    text_inline: null,
    path_rel: null,
    waste_category: null,
    waste_tokens: 0,
  };
}

describe("MCP consultation waterfall rows", () => {
  it("places a privacy-safe marker at its recorded sequence", () => {
    const rows = [1, 2, 3].map((seq) => ({ span: span(seq), depth: 0 }));
    const merged = mergeConsultationRows(rows, [
      {
        event_id: "event-1",
        trace_id: "trace-1",
        after_seq: 2,
        tool_name: "cairn_should_i_stop",
        called_at: "2026-01-01T00:00:00Z",
      },
    ]);

    expect(merged.map((row) => row.span.span_id)).toEqual([
      "span-1",
      "span-2",
      "mcp-event-1",
      "span-3",
    ]);
    expect(merged[2]!.span.name).toBe("agent consulted Cairn here · should I stop");
    expect(merged[2]!.span.text_inline).not.toContain("src/");
  });

  it("hides markers beyond the replay cursor", () => {
    const merged = mergeConsultationRows(
      [{ span: span(1), depth: 0 }],
      [
        {
          event_id: "future",
          trace_id: "trace-1",
          after_seq: 3,
          tool_name: "cairn_project_primer",
          called_at: "2026-01-01T00:00:00Z",
        },
      ],
      1,
    );
    expect(merged).toHaveLength(1);
  });
});
