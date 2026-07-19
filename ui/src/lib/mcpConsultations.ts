import type { McpConsultation, Span } from "@/lib/types";
import type { FlatRow } from "@/lib/waterfallTree";

const FRIENDLY_TOOL_NAMES: Record<string, string> = {
  cairn_have_i_read: "have I read",
  cairn_before_you_read: "before you read",
  cairn_my_recurring_waste: "recurring waste",
  cairn_project_primer: "project primer",
  cairn_session_so_far: "session so far",
  cairn_should_i_stop: "should I stop",
  cairn_project_conventions: "project conventions",
};

export function consultationSpan(event: McpConsultation): Span {
  const tool =
    FRIENDLY_TOOL_NAMES[event.tool_name] ??
    event.tool_name.replace(/^cairn_/, "").replaceAll("_", " ");
  return {
    span_id: `mcp-${event.event_id}`,
    trace_id: event.trace_id,
    parent_span_id: null,
    seq: event.after_seq,
    kind: "system",
    name: `agent consulted Cairn here · ${tool}`,
    agent_id: null,
    agent_lane: null,
    started_at: event.called_at,
    ended_at: event.called_at,
    duration_ms: 0,
    status: "ok",
    model: null,
    input_tokens: 0,
    output_tokens: 0,
    input_estimated: 0,
    output_estimated: 0,
    cache_read_tokens: null,
    cache_creation_tokens: null,
    context_tokens_after: null,
    text_inline:
      "Cairn was consulted through its local MCP server. Tool arguments are not recorded.",
    text_hash: null,
    args_hash: null,
    path_rel: null,
    waste_category: null,
    waste_tokens: 0,
    attrs_json: {},
  };
}

export function mergeConsultationRows(
  rows: FlatRow[],
  consultations: McpConsultation[],
  maxSeq = Number.POSITIVE_INFINITY,
): FlatRow[] {
  const merged = [...rows];
  const visible = consultations
    .filter((event) => event.after_seq <= maxSeq)
    .sort((a, b) => a.after_seq - b.after_seq || a.called_at.localeCompare(b.called_at));
  for (const event of visible) {
    let insertion = 0;
    for (let index = 0; index < merged.length; index += 1) {
      if (merged[index]!.span.seq <= event.after_seq) insertion = index + 1;
    }
    merged.splice(insertion, 0, { span: consultationSpan(event), depth: 0 });
  }
  return merged;
}
