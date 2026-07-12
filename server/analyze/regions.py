"""Context-region decomposition (Phase 4)."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from server.analyze.events import spans_to_events
from server.analyze.views import IncrementalView, trace_input_hash
from server.ingest.pricing_data import match_model
from server.models.context_region import ContextRegion, ContextRegionName
from server.models.span import Span
from server.store.repos.context_regions import ContextRegionRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo

BYTES_PER_TOKEN = 4
TOOL_SCHEMA_TOKENS = 60

_REGIONS = (
    "system",
    "tool_schema",
    "tool_result",
    "retrieved",
    "user",
    "assistant_history",
)
_RETRIEVE_NORMS = frozenset({"search", "grep", "glob"})


@dataclass(frozen=True)
class RegionRow:
    span_id: str
    region: str
    tokens: int
    cost: float
    content_hash: str | None
    first_turn: int
    last_seen_turn: int
    still_in_window: int


@dataclass
class DecomposeResult:
    regions: list[RegionRow] = field(default_factory=list)
    rebilling_tokens: int = 0
    rebilling_cost_usd: float = 0.0
    estimated: bool = True
    data_notes: list[str] = field(default_factory=list)
    turn_count: int = 0


def compute_regions(
    spans: list[Span],
    *,
    model: str | None,
    input_price_per_token: float | None,
) -> DecomposeResult:
    """Compute context-region decomposition for one trace."""
    events = spans_to_events(spans)
    return decompose_session(events, model=model, input_price_per_token=input_price_per_token)


def decompose_session(
    events: list[dict[str, Any]],
    *,
    model: str | None = None,
    input_price_per_token: float | None = None,
) -> DecomposeResult:
    """Decompose session events into per-turn context-region rows."""
    result = DecomposeResult()
    if not events:
        return result

    turns = _split_turns(events)
    if not turns:
        return result
    result.turn_count = len(turns)

    has_real_input = any(
        isinstance(event.get("input_tokens"), (int, float)) and int(event["input_tokens"]) > 0
        for turn in turns
        for event in turn
        if event.get("type") == "assistant_message"
    )
    result.estimated = not has_real_input
    if not has_real_input:
        result.data_notes.append(
            "region tokens estimated from text length (no per-turn input_tokens)"
        )

    seen: dict[str, dict[str, tuple[int, int]]] = {region: {} for region in _REGIONS}
    rebilling_tokens = 0

    for turn_idx, turn in enumerate(turns, start=1):
        assistant_event = _last_assistant(turn)
        if assistant_event is None:
            continue
        span_id = assistant_event.get("span_id")
        if not isinstance(span_id, str) or not span_id:
            continue

        blocks = _build_regions(turn, turns, turn_idx)
        for region_name, (text, tokens, _estimated) in blocks.items():
            if tokens <= 0 and not text:
                continue
            content_hash = _sha256(text) if text else None
            cost = tokens * input_price_per_token if input_price_per_token else 0.0
            prior = seen[region_name].get(content_hash) if content_hash else None
            if prior is not None:
                first_turn = prior[0]
                rebilling_tokens += tokens
            else:
                first_turn = turn_idx
            if content_hash:
                seen[region_name][content_hash] = (first_turn, turn_idx)

            result.regions.append(
                RegionRow(
                    span_id=span_id,
                    region=region_name,
                    tokens=tokens,
                    cost=cost,
                    content_hash=content_hash,
                    first_turn=first_turn,
                    last_seen_turn=turn_idx,
                    still_in_window=1,
                )
            )

    result.rebilling_tokens = rebilling_tokens
    if input_price_per_token is None:
        result.data_notes.append(
            f"input price unknown for model {model or '<unknown>'}; re-billing $ not computed"
        )
    else:
        result.rebilling_cost_usd = round(rebilling_tokens * input_price_per_token, 6)
    return result


def _split_turns(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") == "user_prompt" and current:
            turns.append(current)
            current = []
        current.append(event)
    if current:
        turns.append(current)
    return [
        turn for turn in turns if any(event.get("type") == "assistant_message" for event in turn)
    ]


def _last_assistant(turn: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(turn):
        if event.get("type") == "assistant_message":
            return event
    return None


def _build_regions(
    turn: list[dict[str, Any]],
    all_turns: list[list[dict[str, Any]]],
    turn_idx: int,
) -> dict[str, tuple[str, int, bool]]:
    regions: dict[str, tuple[str, int, bool]] = {}
    turn_idx0 = turn_idx - 1

    tools_so_far: list[str] = []
    seen_tools: set[str] = set()
    for session_turn in all_turns[: turn_idx0 + 1]:
        for event in session_turn:
            tool_norm = event.get("tool_norm_name")
            if event.get("type") != "tool_call" or not isinstance(tool_norm, str):
                continue
            lower_norm = tool_norm.lower()
            if lower_norm in seen_tools:
                continue
            seen_tools.add(lower_norm)
            tools_so_far.append(lower_norm)
    if tools_so_far:
        schema_text = ",".join(sorted(tools_so_far))
        regions["tool_schema"] = (schema_text, len(tools_so_far) * TOOL_SCHEMA_TOKENS, True)

    result_text: list[str] = []
    result_tokens = 0
    retrieved_text: list[str] = []
    retrieved_tokens = 0
    for session_turn in all_turns[: turn_idx0 + 1]:
        for event in session_turn:
            if event.get("type") != "tool_result":
                continue
            tool_norm = str(event.get("tool_norm_name") or "").lower()
            text = str(event.get("text_inline") or "")
            output_tokens = event.get("output_tokens")
            tokens = (
                int(output_tokens)
                if isinstance(output_tokens, (int, float)) and int(output_tokens) > 0
                else _text_tokens(text)
            )
            if tool_norm in _RETRIEVE_NORMS:
                retrieved_text.append(text)
                retrieved_tokens += tokens
            else:
                result_text.append(text)
                result_tokens += tokens
    if result_text:
        regions["tool_result"] = ("\n".join(result_text), result_tokens, True)
    if retrieved_text:
        regions["retrieved"] = ("\n".join(retrieved_text), retrieved_tokens, True)

    user_text = ""
    for event in turn:
        if event.get("type") == "user_prompt":
            user_text = str(event.get("text_inline") or "")
            break
    if user_text:
        regions["user"] = (user_text, _text_tokens(user_text), True)

    history_text: list[str] = []
    history_tokens = 0
    for session_turn in all_turns[:turn_idx0]:
        for event in session_turn:
            if event.get("type") != "assistant_message":
                continue
            text = str(event.get("text_inline") or "")
            output_tokens = event.get("output_tokens")
            tokens = (
                int(output_tokens)
                if isinstance(output_tokens, (int, float)) and int(output_tokens) > 0
                else _text_tokens(text)
            )
            history_text.append(text)
            history_tokens += tokens
    if history_text:
        regions["assistant_history"] = ("\n".join(history_text), history_tokens, True)

    return regions


def _text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text.encode("utf-8")) // BYTES_PER_TOKEN)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _input_price_per_token(model: str | None) -> float | None:
    if not model:
        return None
    row = match_model(model)
    if row is None:
        return None
    return row.input_per_mtok / 1_000_000


def _db_region_name(region: str) -> ContextRegionName:
    if region == "assistant_history":
        return "history"
    if region == "system":
        return "system"
    if region == "tool_schema":
        return "tool_schema"
    if region == "tool_result":
        return "tool_result"
    if region == "retrieved":
        return "retrieved"
    if region == "user":
        return "user"
    if region == "history":
        return "history"
    msg = f"unexpected region: {region}"
    raise ValueError(msg)


class RegionsView(IncrementalView):
    """Populate context_regions rows keyed by trace_id."""

    view_name = "regions"
    VERSION = 1

    def keys_for(self, trace_id: str) -> list[str]:
        return [trace_id]

    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        return trace_input_hash(conn, key)

    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        trace = TraceRepo.get(conn, key)
        if trace is None:
            return
        spans = SpanRepo.list_by_trace(conn, key)
        if not spans:
            ContextRegionRepo.delete_by_trace(conn, key)
            return

        result = compute_regions(
            spans,
            model=trace.model,
            input_price_per_token=_input_price_per_token(trace.model),
        )
        rows: list[ContextRegion] = []
        for region in result.regions:
            rows.append(
                ContextRegion(
                    span_id=region.span_id,
                    region=_db_region_name(region.region),
                    tokens=region.tokens,
                    cost=region.cost,
                    content_hash=region.content_hash,
                    first_turn=region.first_turn,
                    last_seen_turn=region.last_seen_turn,
                    still_in_window=bool(region.still_in_window),
                )
            )
        ContextRegionRepo.delete_by_trace(conn, key)
        ContextRegionRepo.upsert_many(conn, rows)
