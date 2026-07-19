import { describe, expect, it } from "vitest";
import { interpolateReplayAtSeq } from "@/lib/replay";
import type { ReplayCheckpoint } from "@/lib/types";

function mkCheckpoint(seq: number): ReplayCheckpoint {
  const spans = Array.from({ length: seq }, (_, i) => ({
    span_id: `s${i + 1}`,
    trace_id: "t1",
    parent_span_id: null,
    seq: i + 1,
    kind: "user_msg" as const,
    name: "turn",
    agent_id: null,
    agent_lane: null,
    started_at: null,
    ended_at: null,
    duration_ms: 10,
    status: "ok" as const,
    model: null,
    input_tokens: 10,
    output_tokens: 5,
    input_estimated: 0,
    output_estimated: 0,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    context_tokens_after: (i + 1) * 100,
    text_inline: null,
    text_hash: null,
    args_hash: null,
    path_rel: null,
    waste_category: null,
    waste_tokens: 0,
    attrs_json: {},
  }));
  return {
    seq,
    spans,
    summary: {
      turn: seq,
      context_tokens: seq * 100,
      cost: 0,
      cost_estimated: false,
      files_read: 0,
      agents: 0,
    },
  };
}

describe("interpolateReplayAtSeq", () => {
  const checkpoints = [mkCheckpoint(40), mkCheckpoint(80), mkCheckpoint(100)];

  it("filters spans between checkpoints", () => {
    const { spans, summary } = interpolateReplayAtSeq(checkpoints, 50);
    expect(spans).toHaveLength(50);
    expect(spans[49]?.seq).toBe(50);
    expect(summary.turn).toBe(50);
    expect(summary.context_tokens).toBe(5000);
  });

  it("returns empty at seq zero", () => {
    const { spans } = interpolateReplayAtSeq(checkpoints, 0);
    expect(spans).toHaveLength(0);
  });
});
