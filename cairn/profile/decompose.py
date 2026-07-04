"""Context-region decomposition (Part 8 + §2.7C)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

BYTES_PER_TOKEN = 4
# A tool definition is roughly this many tokens of JSON schema in the request.
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


@dataclass
class RegionRow:
    event_id: int
    region: str
    tokens: int
    cost: float
    content_hash: str | None
    first_turn: int
    last_seen_turn: int
    still_in_window: int
    estimated: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "region": self.region,
            "tokens": self.tokens,
            "cost": self.cost,
            "content_hash": self.content_hash,
            "first_turn": self.first_turn,
            "last_seen_turn": self.last_seen_turn,
            "still_in_window": self.still_in_window,
            "estimated": self.estimated,
        }


@dataclass
class DecomposeResult:
    regions: list[RegionRow] = field(default_factory=list)
    rebilling_tokens: int = 0
    rebilling_cost_usd: float = 0.0
    estimated: bool = True
    data_notes: list[str] = field(default_factory=list)
    turn_count: int = 0


def decompose_session(
    events: list[dict[str, Any]],
    *,
    model: str | None = None,
    input_price_per_token: float | None = None,
) -> DecomposeResult:
    """Decompose a session's events into per-turn context regions.

    ``input_price_per_token`` is the model's input price used to convert
    re-billed tokens into recoverable dollars. When unknown, re-billing tokens
    are still recorded but the dollar value stays 0.0 with a data-note.
    """
    result = DecomposeResult()
    if not events:
        return result

    turns = _split_turns(events)
    if not turns:
        return result
    result.turn_count = len(turns)

    has_real_input = any(
        isinstance(e.get("input_tokens"), (int, float)) and int(e["input_tokens"]) > 0
        for turn in turns
        for e in turn
        if e.get("type") == "assistant_message"
    )
    result.estimated = not has_real_input
    if not has_real_input:
        result.data_notes.append(
            "region tokens estimated from text length (no per-turn input_tokens)"
        )

    # Track each region's content hash across turns to detect re-billing.
    # region -> content_hash -> (first_turn, last_turn)
    seen: dict[str, dict[str, tuple[int, int]]] = {r: {} for r in _REGIONS}
    rebilling_tokens = 0

    for turn_idx, turn in enumerate(turns, start=1):
        assistant_event = _last_assistant(turn)
        if assistant_event is None:
            continue
        event_id = int(assistant_event.get("event_id") or 0)
        if event_id == 0:
            continue

        price = input_price_per_token or 0.0
        blocks = _build_regions(turn, turns, turn_idx)

        for region_name, (text, tokens, estimated) in blocks.items():
            if tokens <= 0 and not text:
                continue
            content_hash = _sha256(text) if text else None
            cost = tokens * price if price else 0.0
            prior = seen[region_name].get(content_hash) if content_hash else None
            if prior is not None:
                first_turn = prior[0]
                # Same block re-sent this turn → re-billed.
                rebilling_tokens += tokens
            else:
                first_turn = turn_idx
            if content_hash:
                seen[region_name][content_hash] = (first_turn, turn_idx)
            result.regions.append(
                RegionRow(
                    event_id=event_id,
                    region=region_name,
                    tokens=tokens,
                    cost=cost,
                    content_hash=content_hash,
                    first_turn=first_turn,
                    last_seen_turn=turn_idx,
                    still_in_window=1,  # present in this turn's assembled context
                    estimated=1 if (estimated or not has_real_input) else 0,
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
    """Group events into turns delimited by ``user_prompt``."""
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") == "user_prompt" and current:
            turns.append(current)
            current = []
        current.append(event)
    if current:
        turns.append(current)
    # A turn must contain an assistant response to count as an assembled turn.
    return [t for t in turns if any(e.get("type") == "assistant_message" for e in t)]


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
    """Return {region: (text, tokens, estimated)} for this assistant turn."""
    regions: dict[str, tuple[str, int, bool]] = {}
    turn_idx0 = turn_idx - 1

    # system: not captured in flattened events — omitted with honesty.
    # (No evidence in the ledger; emitting 0 would fabricate a value.)

    # tool_schema: union of tools defined so far in the session.
    tools_so_far: list[str] = []
    seen_tools: set[str] = set()
    for t in all_turns[: turn_idx0 + 1]:
        for e in t:
            norm = e.get("tool_norm_name")
            if e.get("type") == "tool_call" and norm and norm not in seen_tools:
                seen_tools.add(norm)
                tools_so_far.append(str(norm))
    if tools_so_far:
        schema_text = ",".join(sorted(tools_so_far))
        regions["tool_schema"] = (schema_text, len(tools_so_far) * TOOL_SCHEMA_TOKENS, True)

    # tool_result + retrieved: results from prior tool calls still in window
    # plus this turn's results.
    result_text: list[str] = []
    result_tokens = 0
    retrieved_text: list[str] = []
    retrieved_tokens = 0
    for t in all_turns[: turn_idx0 + 1]:
        for e in t:
            if e.get("type") != "tool_result":
                continue
            norm = e.get("tool_norm_name")
            text = str(e.get("text_inline") or "")
            out_tok = e.get("output_tokens")
            tok = (
                int(out_tok)
                if isinstance(out_tok, (int, float)) and int(out_tok) > 0
                else _text_tokens(text)
            )
            if norm in _RETRIEVE_NORMS:
                retrieved_text.append(text)
                retrieved_tokens += tok
            else:
                result_text.append(text)
                result_tokens += tok
    if result_text:
        regions["tool_result"] = ("\n".join(result_text), result_tokens, True)
    if retrieved_text:
        regions["retrieved"] = ("\n".join(retrieved_text), retrieved_tokens, True)

    # user: the current turn's user prompt.
    user_text = ""
    for e in turn:
        if e.get("type") == "user_prompt":
            user_text = str(e.get("text_inline") or "")
            break
    if user_text:
        regions["user"] = (user_text, _text_tokens(user_text), True)

    # assistant_history: all prior assistant messages.
    hist_text: list[str] = []
    hist_tokens = 0
    for t in all_turns[:turn_idx0]:
        for e in t:
            if e.get("type") == "assistant_message":
                text = str(e.get("text_inline") or "")
                out_tok = e.get("output_tokens")
                tok = (
                    int(out_tok)
                    if isinstance(out_tok, (int, float)) and int(out_tok) > 0
                    else _text_tokens(text)
                )
                hist_text.append(text)
                hist_tokens += tok
    if hist_text:
        regions["assistant_history"] = ("\n".join(hist_text), hist_tokens, True)

    return regions


def _text_tokens(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text.encode("utf-8")) // BYTES_PER_TOKEN)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
