import type { ReplayCheckpoint, ReplayResponse, Span } from "@/lib/types";

export function interpolateReplayAtSeq(
  checkpoints: ReplayCheckpoint[],
  seq: number,
): { spans: Span[]; summary: Record<string, unknown> } {
  if (checkpoints.length === 0 || seq <= 0) {
    return { spans: [], summary: { turn: 0 } };
  }
  const anchor = checkpoints.find((cp) => cp.seq >= seq) ?? checkpoints[checkpoints.length - 1]!;
  const spans = anchor.spans.filter((s) => s.seq <= seq);
  const ctx = [...spans].reverse().find((s) => s.context_tokens_after)?.context_tokens_after;
  const files = new Set(spans.map((s) => s.path_rel).filter(Boolean)).size;
  const agents = new Set(spans.map((s) => s.agent_id).filter(Boolean)).size;
  return {
    spans,
    summary: {
      turn: seq,
      context_tokens: ctx ?? null,
      cost: anchor.summary.cost ?? null,
      files_read: files,
      agents,
    },
  };
}

export function isCheckpointReplay(data: ReplayResponse): data is ReplayResponse & {
  checkpoints: ReplayCheckpoint[];
} {
  return Array.isArray(data.checkpoints) && data.checkpoints.length > 0;
}
