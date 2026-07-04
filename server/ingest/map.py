"""Map parsed sessions to Trace + Span models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from server.ingest.adapters.claude_code import ToolCallDraft
from server.ingest.normalizer import assign_seq
from server.ingest.project_paths import path_rel_to_repo, try_git_branch, try_git_commit
from server.ingest.quality import PARSER_VERSION, compute_data_quality
from server.ingest.usage import ObservedUsage, extract_usage_dict
from server.models.data_quality import DataQuality
from server.models.span import Span, SpanKind, SpanStatus
from server.models.trace import Trace
from server.util.hash import hash_obj

_TEXT_INLINE_MAX = 500
_HAS_COST_SOURCES = frozenset({"claude-code", "claude_code", "codex", "cursor"})
_EVENT_TO_KIND: dict[str, SpanKind] = {
    "user_prompt": "user_msg",
    "assistant_message": "assistant_msg",
    "tool_call": "tool_call",
    "tool_result": "tool_result",
    "error": "system",
    "file_snapshot": "retrieval",
    "sub_agent": "subagent",
    "session_start": "agent",
    "token_count": "system",
    "compaction": "compaction",
}


@dataclass(frozen=True)
class ParsedSession:
    """Normalized parser output before DB write."""

    source: str
    external_id: str
    cwd: str | None
    git_branch: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    events: list[dict[str, Any]]
    tool_calls: list[ToolCallDraft]
    usage: ObservedUsage
    has_cost: bool | None = None
    status: str = "completed"
    context_window: int | None = None
    dropped_events: int = 0


def normalize_source(source: str) -> str:
    """Map legacy source ids to schema ids."""
    return source.replace("-", "_")


def stable_trace_id(source: str, external_id: str, workspace_id: str) -> str:
    """Deterministic trace id from source + external_id."""
    digest = hash_obj({"workspace_id": workspace_id, "source": source, "external_id": external_id})
    return digest[:26].upper()


def stable_span_id(trace_id: str, seq: int) -> str:
    """Deterministic span id from trace + sequence."""
    digest = hash_obj({"trace_id": trace_id, "seq": seq})
    return digest[:26].upper()


def _truncate_inline(text: str | None) -> str | None:
    if not text:
        return None
    return text if len(text) <= _TEXT_INLINE_MAX else text[:_TEXT_INLINE_MAX]


def _event_text(event: dict[str, Any]) -> tuple[str | None, str | None]:
    for key in ("text_inline", "text"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return event.get("text_hash"), _truncate_inline(val)
    for key in ("args_inline", "result_inline"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return event.get("args_hash") or event.get("result_hash"), _truncate_inline(val)
        if isinstance(val, dict):
            return event.get("args_hash"), json.dumps(val, sort_keys=True)[:_TEXT_INLINE_MAX]
    return event.get("text_hash") or event.get("args_hash"), None


def _path_from_tool_input(
    event: dict[str, Any], cwd: str | None, root: Path
) -> str | None:
    for key in ("path", "file_path", "file", "filename"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return path_rel_to_repo(root, val)
    args = event.get("args_inline") or event.get("input")
    if isinstance(args, dict):
        for key in ("path", "file_path", "file", "filename"):
            val = args.get(key)
            if isinstance(val, str) and val:
                return path_rel_to_repo(root, val)
    return None


def flatten_event(
    event: dict[str, Any],
    *,
    source: str,
    tool_by_id: dict[str, ToolCallDraft],
    cwd: str | None,
    root: Path,
) -> dict[str, Any]:
    """Normalize one parser event to span fields."""
    etype = str(event.get("type", "unknown"))
    text_hash, text_inline = _event_text(event)
    tool_name = event.get("tool_name") or event.get("name")
    path_rel = event.get("path_rel")
    tool_is_error = bool(event.get("is_error"))

    if etype == "tool_call" and isinstance(tool_name, str):
        draft = tool_by_id.get(str(event.get("tool_use_id", "")))
        if draft and draft.path_rel:
            path_rel = draft.path_rel
        elif not path_rel:
            path_rel = _path_from_tool_input(event, cwd, root)

    if etype == "tool_result":
        draft = tool_by_id.get(str(event.get("tool_use_id", "")))
        if draft:
            tool_name = draft.name
            path_rel = path_rel or draft.path_rel

    usage = event.get("usage") if isinstance(event.get("usage"), dict) else {}
    obs = extract_usage_dict(usage) if usage else ObservedUsage()

    return {
        "seq": int(event["seq"]),
        "type": etype,
        "tool_use_id": event.get("tool_use_id"),
        "name": tool_name if isinstance(tool_name, str) else etype,
        "text_hash": text_hash,
        "text_inline": text_inline,
        "args_hash": event.get("args_hash"),
        "path_rel": path_rel,
        "tool_is_error": tool_is_error,
        "input_tokens": obs.input_tokens or event.get("input_tokens"),
        "output_tokens": obs.output_tokens or event.get("output_tokens"),
        "input_estimated": 1 if (obs.input_estimated or event.get("input_estimated")) else 0,
        "output_estimated": 1 if (obs.output_estimated or event.get("output_estimated")) else 0,
        "cache_read_tokens": obs.cache_read_tokens or event.get("cache_read_tokens"),
        "cache_creation_tokens": obs.cache_creation_tokens or event.get("cache_creation_tokens"),
        "context_tokens_after": event.get("context_tokens_after"),
        "duration_ms": event.get("duration_ms"),
        "started_at": event.get("ts") or event.get("timestamp"),
        "agent_id": event.get("agent_id"),
        "agent_lane": event.get("agent_lane"),
        "model": event.get("model"),
        "attrs": {k: v for k, v in event.items() if k.startswith("gen_ai.")},
    }


def _span_kind(etype: str) -> SpanKind:
    return _EVENT_TO_KIND.get(etype, "system")


def _span_status(row: dict[str, Any]) -> SpanStatus:
    if row.get("tool_is_error") or row["type"] == "error":
        return "error"
    return "ok"


def _title_from_events(events: list[dict[str, Any]]) -> str | None:
    for event in events:
        if event.get("type") == "user_prompt":
            text = event.get("text_inline") or event.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()[:120]
    return None


def _project_name(cwd: str | None, root: Path) -> str | None:
    if not cwd:
        return root.name
    try:
        return Path(cwd).resolve().name
    except OSError:
        return None


def _peak_context_pct(events: list[dict[str, Any]], context_window: int | None) -> float | None:
    peak = 0
    for event in events:
        ctx = event.get("context_tokens_after")
        if isinstance(ctx, int) and ctx > 0:
            peak = max(peak, ctx)
    if peak <= 0:
        return None
    window = context_window or 200_000
    return round(peak / window * 100, 1) if window > 0 else None


def _dominant_model(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        model = event.get("model")
        if isinstance(model, str) and model:
            return model
    return None


def _observed_usage_from_events(events: list[dict[str, Any]]) -> ObservedUsage:
    total = ObservedUsage()
    for event in events:
        usage = event.get("usage")
        if isinstance(usage, dict):
            total.add(extract_usage_dict(usage))
        if event.get("type") == "assistant_message":
            inp = event.get("input_tokens")
            out = event.get("output_tokens")
            partial = ObservedUsage()
            if isinstance(inp, int):
                partial.input_tokens = inp
            if isinstance(out, int):
                partial.output_tokens = out
            total.add(partial)
    return total


def session_to_trace_spans(
    parsed: ParsedSession,
    *,
    workspace_id: str,
    repo_root: Path,
    pricing_overrides: dict[str, dict[str, object]] | None = None,
) -> tuple[Trace, list[Span], DataQuality]:
    """Convert a parsed session into trace, spans, and data quality."""
    from server.ingest.pricing import estimate_cost

    source = normalize_source(parsed.source)
    trace_id = stable_trace_id(source, parsed.external_id, workspace_id)
    seq_events = assign_seq(parsed.events)
    tool_by_id = {tc.tool_use_id: tc for tc in parsed.tool_calls}
    flat_rows = [
        flatten_event(event, source=source, tool_by_id=tool_by_id, cwd=parsed.cwd, root=repo_root)
        for event in seq_events
    ]

    observed = (
        parsed.usage if parsed.usage.input_tokens else _observed_usage_from_events(seq_events)
    )
    model = parsed.model or _dominant_model(seq_events) or source
    cost_flag = (
        parsed.has_cost
        if parsed.has_cost is not None
        else source.replace("_", "-") in _HAS_COST_SOURCES
    )

    total_cost = 0.0
    cost_source: Literal["absent", "observed", "priced"] = "absent"
    if cost_flag:
        if observed.cost is not None:
            total_cost = observed.cost
            cost_source = "observed"
        else:
            breakdown = estimate_cost(model, observed, overrides=pricing_overrides)
            total_cost = breakdown.total
            cost_source = "priced" if breakdown.total > 0 else "absent"

    tool_calls = sum(1 for r in flat_rows if r["type"] == "tool_call")
    tool_errors = sum(1 for r in flat_rows if r.get("tool_is_error"))
    project = _project_name(parsed.cwd, repo_root)
    git_commit = try_git_commit(repo_root)
    branch = parsed.git_branch or try_git_branch(repo_root)
    started = parsed.started_at or datetime.now(UTC).isoformat()

    trace = Trace(
        trace_id=trace_id,
        workspace_id=workspace_id,
        source=source,
        external_id=parsed.external_id,
        project=project,
        cwd=parsed.cwd,
        model=model,
        git_branch=branch,
        git_commit=git_commit,
        started_at=started,
        ended_at=parsed.ended_at,
        status=parsed.status,
        title=_title_from_events(seq_events),
        input_tokens=observed.input_tokens or 0,
        output_tokens=observed.output_tokens or 0,
        cache_read_tokens=observed.cache_read_tokens or 0,
        cache_creation_tokens=observed.cache_creation_tokens or 0,
        reasoning_tokens=observed.reasoning_tokens or 0,
        cost=total_cost,
        cost_source=cost_source,
        context_window=parsed.context_window,
        peak_context_pct=_peak_context_pct(seq_events, parsed.context_window),
        span_count=len(flat_rows),
        tool_calls=tool_calls,
        tool_errors=tool_errors,
    )

    tool_call_parents: dict[str, str] = {}
    spans: list[Span] = []
    for row in flat_rows:
        span_id = stable_span_id(trace_id, row["seq"])
        parent_id: str | None = None
        if row["type"] == "tool_result":
            parent_id = tool_call_parents.get(str(row.get("tool_use_id", "")))
        elif row["type"] == "tool_call":
            tool_call_parents[str(row.get("tool_use_id", ""))] = span_id

        spans.append(
            Span(
                span_id=span_id,
                trace_id=trace_id,
                parent_span_id=parent_id,
                seq=row["seq"],
                kind=_span_kind(row["type"]),
                name=row.get("name"),
                agent_id=row.get("agent_id"),
                agent_lane=row.get("agent_lane"),
                started_at=row.get("started_at"),
                duration_ms=row.get("duration_ms"),
                status=_span_status(row),
                model=row.get("model"),
                input_tokens=row.get("input_tokens"),
                output_tokens=row.get("output_tokens"),
                input_estimated=row.get("input_estimated", 0),
                output_estimated=row.get("output_estimated", 0),
                cache_read_tokens=row.get("cache_read_tokens"),
                cache_creation_tokens=row.get("cache_creation_tokens"),
                context_tokens_after=row.get("context_tokens_after"),
                text_inline=row.get("text_inline"),
                text_hash=row.get("text_hash"),
                args_hash=row.get("args_hash"),
                path_rel=row.get("path_rel"),
                attrs_json=row.get("attrs") or {},
            )
        )

    quality_row = compute_data_quality(
        flat_rows=flat_rows,
        observed=observed,
        has_cost=cost_flag,
        has_timestamps=bool(parsed.started_at),
        cost_was_priced=cost_source == "priced",
        dropped_events=parsed.dropped_events,
    )
    quality = DataQuality(
        trace_id=trace_id,
        pct_tokens_measured=quality_row.get("pct_tokens_measured"),
        pct_tokens_estimated=quality_row.get("pct_tokens_estimated"),
        timestamps_present=bool(quality_row.get("timestamps_present")),
        cost_source=str(quality_row.get("cost_source", "absent")),
        parser_version=PARSER_VERSION,
        dropped_events=int(quality_row.get("dropped_events", 0)),
        notes=_parse_notes(quality_row.get("notes_json")) or {},
        computed_at=datetime.now(UTC).isoformat(),
    )
    return trace, spans, quality


def _parse_notes(raw: object) -> dict[str, object] | None:
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {"messages": parsed}
        except json.JSONDecodeError:
            return {"message": raw}
    if isinstance(raw, list):
        return {"messages": raw}
    return None
