"""Convert trace spans to legacy event dicts for ported analyzers."""

from __future__ import annotations

from typing import Any

from server.models.span import Span

_KIND_TO_TYPE: dict[str, str] = {
    "user_msg": "user_prompt",
    "assistant_msg": "assistant_message",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "retrieval": "file_snapshot",
    "subagent": "sub_agent",
    "compaction": "compaction",
    "system": "error",
    "agent": "session_start",
    "llm_call": "assistant_message",
}


def spans_to_events(spans: list[Span]) -> list[dict[str, Any]]:
    """Map v4 spans to legacy ingest event shape."""
    events: list[dict[str, Any]] = []
    for span in spans:
        event_type = _KIND_TO_TYPE.get(span.kind, span.kind)
        tool_norm = span.name if span.kind in {"tool_call", "tool_result"} else None
        events.append(
            {
                "seq": span.seq,
                "type": event_type,
                "tool_norm_name": tool_norm,
                "tool_is_error": span.status == "error",
                "input_tokens": span.input_tokens,
                "output_tokens": span.output_tokens,
                "input_estimated": span.input_estimated,
                "output_estimated": span.output_estimated,
                "context_tokens_after": span.context_tokens_after,
                "text_inline": span.text_inline,
                "text_hash": span.text_hash,
                "args_hash": span.args_hash,
                "path_rel": span.path_rel,
                "waste_category": span.waste_category,
                "waste_tokens": span.waste_tokens,
            }
        )
    return events
