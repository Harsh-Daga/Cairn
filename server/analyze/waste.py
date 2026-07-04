"""Waste token taxonomy analyzer."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from server.analyze.constants import CONTEXT_ROT_WASTE_PCT

BYTES_PER_TOKEN = 4
OVERSIZE_TOKEN_THRESHOLD = 8000
OVERSIZE_TOKEN_BASE = 4000


def context_rot_waste_pct() -> float:
    return CONTEXT_ROT_WASTE_PCT


def context_rot_warning_pct() -> float:
    return CONTEXT_ROT_WASTE_PCT


@dataclass
class WasteResult:
    tags: list[tuple[int, str, int]] = field(default_factory=list)
    total_waste_tokens: int = 0
    run_level: list[str] = field(default_factory=list)

    def by_category(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for _, cat, tokens in self.tags:
            out[cat] += tokens
        return dict(out)


def compute_waste(
    events: list[dict[str, Any]],
    *,
    has_cost: bool = True,
    has_timestamps: bool = True,
    peak_context_pct: float | None = None,
    rebilling_tokens: int | None = None,
) -> WasteResult:
    """Classify waste across session events.

    ``peak_context_pct`` / ``rebilling_tokens`` are optional run-level inputs
    (the profiler supplies rebilling in Phase B). When omitted, CONTEXT_ROT is
    derived from per-event ``context_tokens_after`` against a 200k default.
    """
    if not events:
        return WasteResult()

    tags: dict[int, tuple[str, int]] = {}

    _tag_identical_calls(events, tags, has_cost=has_cost)
    _tag_retry_loops(events, tags, has_cost=has_cost)
    _tag_oversize_results(events, tags, has_cost=has_cost)
    _tag_stale_context(events, tags, has_cost=has_cost)
    _tag_orientation_waste(events, tags, has_cost=has_cost)
    _tag_blind_retry(events, tags, has_cost=has_cost)
    _tag_uncleared_tool_results(events, tags, has_cost=has_cost)

    run_level: list[str] = []
    if _has_context_rot(events, peak_context_pct):
        run_level.append("context_rot")
        # Attribute an estimate to the last 20% of events (degradation tail).
        if has_cost:
            tail = max(1, len(events) // 5)
            for event in events[-tail:]:
                seq = int(event.get("seq", 0))
                if seq and seq not in tags:
                    inp = _tokens(event)
                    if inp > 0:
                        tags[seq] = ("context_rot", inp)

    if rebilling_tokens and rebilling_tokens > 0:
        run_level.append("rebilling_waste")

    result_tags = [(seq, cat, tok) for seq, (cat, tok) in sorted(tags.items())]
    total = sum(t for _, _, t in result_tags)
    if rebilling_tokens and rebilling_tokens > 0:
        total += int(rebilling_tokens)
    return WasteResult(tags=result_tags, total_waste_tokens=total, run_level=run_level)


def _tokens(event: dict[str, Any], field_name: str = "input_tokens") -> int:
    val = event.get(field_name)
    if isinstance(val, (int, float)) and val > 0:
        return int(val)
    return 0


def _event_by_seq(events: list[dict[str, Any]], seq: int) -> dict[str, Any]:
    for event in events:
        if int(event.get("seq", -1)) == seq:
            return event
    return {}


def _tag_identical_calls(
    events: list[dict[str, Any]],
    tags: dict[int, tuple[str, int]],
    *,
    has_cost: bool,
) -> None:
    """IDENTICAL_CALL: same tool + args_hash, non-consecutive (≥3 dups cap)."""
    by_sig: dict[tuple[str, str], list[int]] = defaultdict(list)
    for event in events:
        if event.get("type") != "tool_call":
            continue
        norm = event.get("tool_norm_name")
        args_hash = event.get("args_hash") or event.get("text_hash")
        if not norm or not args_hash:
            continue
        by_sig[(str(norm), str(args_hash))].append(int(event.get("seq", 0)))

    for (_norm, _hash), call_seqs in by_sig.items():
        if len(call_seqs) < 2:
            continue
        call_seqs.sort()
        # Skip bash with differing outputs is handled by args_hash equality.
        for i in range(1, len(call_seqs)):
            prev_seq = call_seqs[i - 1]
            cur_seq = call_seqs[i]
            if cur_seq - prev_seq <= 1:
                continue
            event = _event_by_seq(events, cur_seq)
            waste = _tokens(event) if has_cost else 0
            tags[cur_seq] = ("identical_call", waste)


def _tag_blind_retry(
    events: list[dict[str, Any]],
    tags: dict[int, tuple[str, int]],
    *,
    has_cost: bool,
) -> None:
    """BLIND_RETRY: same tool + args within ≤2 turns (§2.7C Lucky-Pass signal)."""
    by_sig: dict[tuple[str, str], list[int]] = defaultdict(list)
    for event in events:
        if event.get("type") != "tool_call":
            continue
        norm = event.get("tool_norm_name")
        args_hash = event.get("args_hash") or event.get("text_hash")
        if not norm or not args_hash:
            continue
        by_sig[(str(norm), str(args_hash))].append(int(event.get("seq", 0)))

    for _sig, call_seqs in by_sig.items():
        if len(call_seqs) < 2:
            continue
        call_seqs.sort()
        for i in range(1, len(call_seqs)):
            prev_seq = call_seqs[i - 1]
            cur_seq = call_seqs[i]
            gap = cur_seq - prev_seq
            if 0 < gap <= 2:
                event = _event_by_seq(events, cur_seq)
                waste = _tokens(event) if has_cost else 0
                # Don't overwrite a stronger identical_call tag.
                tags.setdefault(cur_seq, ("blind_retry", waste))


def _tag_retry_loops(
    events: list[dict[str, Any]],
    tags: dict[int, tuple[str, int]],
    *,
    has_cost: bool,
) -> None:
    """RETRY_LOOP: tool_call → error result → same tool within 3 events."""
    retry_counts: dict[str, int] = defaultdict(int)
    indexed = {int(e["seq"]): e for e in events if "seq" in e}
    seq_list = sorted(indexed)

    for i, seq in enumerate(seq_list):
        event = indexed[seq]
        if event.get("type") != "tool_call":
            continue
        norm = event.get("tool_norm_name")
        if not norm:
            continue
        window = seq_list[i + 1 : i + 4]
        saw_error = False
        for wseq in window:
            w = indexed[wseq]
            if w.get("type") == "tool_result" and w.get("tool_is_error"):
                saw_error = True
            if (
                saw_error
                and w.get("type") == "tool_call"
                and w.get("tool_norm_name") == norm
                and retry_counts[str(norm)] < 5
            ):
                retry_counts[str(norm)] += 1
                waste = (_tokens(w) + _tokens(w, "output_tokens")) if has_cost else 0
                tags[int(w["seq"])] = ("retry_loop", waste)
                break


def _tag_oversize_results(
    events: list[dict[str, Any]],
    tags: dict[int, tuple[str, int]],
    *,
    has_cost: bool,
) -> None:
    for event in events:
        if event.get("type") != "tool_result":
            continue
        out = _tokens(event, "output_tokens")
        if out <= 0:
            inline = event.get("text_inline") or ""
            out = len(str(inline).encode("utf-8")) // BYTES_PER_TOKEN
        if out <= OVERSIZE_TOKEN_THRESHOLD:
            continue
        waste = max(0, out - OVERSIZE_TOKEN_BASE) if has_cost else 0
        tags[int(event.get("seq", 0))] = ("oversize_result", waste)


def _tag_stale_context(
    events: list[dict[str, Any]],
    tags: dict[int, tuple[str, int]],
    *,
    has_cost: bool,
) -> None:
    file_reads: dict[str, list[int]] = defaultdict(list)
    file_edits: dict[str, set[int]] = defaultdict(set)

    for event in events:
        path = event.get("path_rel")
        if not path:
            continue
        seq = int(event.get("seq", 0))
        norm = event.get("tool_norm_name")
        if event.get("type") == "file_snapshot" or (
            event.get("type") == "tool_call" and norm == "read"
        ):
            file_reads[str(path)].append(seq)
        if event.get("type") == "tool_call" and norm == "edit":
            file_edits[str(path)].add(seq)

    for path, reads in file_reads.items():
        if len(reads) < 2:
            continue
        for i in range(1, len(reads)):
            prev_seq = reads[i - 1]
            cur_seq = reads[i]
            gap = cur_seq - prev_seq
            if gap <= 2:
                continue
            edited_between = any(prev_seq < e < cur_seq for e in file_edits.get(path, set()))
            if edited_between:
                continue
            event = _event_by_seq(events, cur_seq)
            waste = _tokens(event) if has_cost else 0
            tags[cur_seq] = ("stale_context", waste)


def _tag_orientation_waste(
    events: list[dict[str, Any]],
    tags: dict[int, tuple[str, int]],
    *,
    has_cost: bool,
) -> None:
    turns = _group_turns(events)
    if len(turns) <= 10:
        return
    first_three = turns[:3]
    read_search = 0
    edits = 0
    total_calls = 0
    orientation_seqs: list[int] = []

    for turn in first_three:
        for event in turn:
            if event.get("type") != "tool_call":
                continue
            total_calls += 1
            norm = event.get("tool_norm_name")
            if norm in ("read", "search"):
                read_search += 1
                orientation_seqs.append(int(event.get("seq", 0)))
            elif norm == "edit":
                edits += 1

    if total_calls == 0 or read_search / total_calls <= 0.6 or edits > 0:
        return
    for seq in orientation_seqs:
        event = _event_by_seq(events, seq)
        waste = _tokens(event) if has_cost else 0
        if seq not in tags:
            tags[seq] = ("orientation_waste", waste)


def _tag_uncleared_tool_results(
    events: list[dict[str, Any]],
    tags: dict[int, tuple[str, int]],
    *,
    has_cost: bool,
) -> None:
    """UNCLEARED_TOOL_RESULT (§2.7C): re-fetchable result still in window ≥3
    turns after it was produced, with no later edit depending on it."""
    indexed = {int(e["seq"]): e for e in events if "seq" in e}
    seq_list = sorted(indexed)
    tool_results: list[tuple[int, str | None]] = []  # (seq, path_rel)
    defaultdict(set)

    for event in events:
        if event.get("type") == "tool_result":
            seq = int(event.get("seq", 0))
            # Only re-fetchable results: reads/searches (have a path_rel).
            tool_results.append((seq, event.get("path_rel")))

    for seq, path in tool_results:
        if not path:
            continue
        # Is there a later edit to the same path? If so, the result may be relied on.
        later_edit = any(
            e_seq > seq
            and e.get("type") == "tool_call"
            and e.get("tool_norm_name") == "edit"
            and e.get("path_rel") == path
            for e_seq, e in indexed.items()
        )
        if later_edit:
            continue
        # ≥3 turns (events) after produced, still no dependency → uncleared.
        later = [s for s in seq_list if s > seq]
        if len(later) < 3:
            continue
        event = _event_by_seq(events, seq)
        inline = event.get("text_inline") or ""
        size = len(str(inline).encode("utf-8")) // BYTES_PER_TOKEN
        waste = size if has_cost else 0
        tags.setdefault(seq, ("uncleared_tool_result", waste))


def _has_context_rot(events: list[dict[str, Any]], peak_context_pct: float | None) -> bool:
    if peak_context_pct is not None:
        return float(peak_context_pct) > context_rot_waste_pct()
    peak = 0
    for event in events:
        ctx = event.get("context_tokens_after")
        if isinstance(ctx, (int, float)) and ctx > 0:
            peak = max(peak, int(ctx))
    if peak <= 0:
        return False
    return peak / 200_000 * 100 > context_rot_waste_pct()


def _group_turns(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    turns: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for event in events:
        if event.get("type") == "user_prompt" and current:
            turns.append(current)
            current = []
        current.append(event)
    if current:
        turns.append(current)
    return turns
