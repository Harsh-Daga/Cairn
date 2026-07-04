"""Context-waste detectors (Part 8 + §2.7C)."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from cairn.profile.decompose import _RETRIEVE_NORMS, RegionRow, _text_tokens

_NEAR_DUP_THRESHOLD = 0.85
_REDUNDANT_OVERLAP = 0.15
_STALE_TURNS = 3
_DUPLICATE_TURNS = 3
_RARE_USE_FRACTION = 0.1
_CONTEXT_FILL_WARN_PCT = 70.0  # §2.7C profiler warning (85% = run-level CONTEXT_ROT in waste.py)
_WORD_RE = re.compile(r"[A-Za-z0-9_./-]+")


@dataclass
class Finding:
    type: str
    severity: str
    tokens: int
    cost_usd: float
    fix: str
    detail: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "tokens": self.tokens,
            "cost_usd": self.cost_usd,
            "fix": self.fix,
            "detail": self.detail,
        }


def detect_findings(
    events: list[dict[str, Any]],
    regions: list[RegionRow],
    *,
    input_price_per_token: float | None = None,
    peak_context_pct: float | None = None,
) -> list[Finding]:
    """Run all detectors over the decomposed regions."""
    price = input_price_per_token or 0.0
    findings: list[Finding] = []
    findings.extend(_dup_regions(regions, price))
    findings.extend(_near_duplicate(events, regions, price))
    findings.extend(_stale_tool_result(events, regions, price))
    findings.extend(_unused_tool_schema(events, regions, price))
    findings.extend(_redundant_fetch(events, regions, price))
    fill = detect_context_fill_warning(peak_context_pct)
    if fill is not None:
        findings.append(fill)
    return findings


def detect_context_fill_warning(peak_context_pct: float | None) -> Finding | None:
    """§2.7C: warn at ≥70% context fill — compaction/clearing recommended."""
    if peak_context_pct is None or float(peak_context_pct) < _CONTEXT_FILL_WARN_PCT:
        return None
    pct = float(peak_context_pct)
    severity = "high" if pct > 85 else "medium"
    return Finding(
        type="CONTEXT_FILL_WARNING",
        severity=severity,
        tokens=0,
        cost_usd=0.0,
        fix="run /compact, clear consumed tool results, or split the task before context rot",
        detail={"peak_context_pct": pct, "threshold_pct": _CONTEXT_FILL_WARN_PCT},
    )


def rebilling_waste_tokens(
    events: list[dict[str, Any]],
    regions: list[RegionRow],
) -> int:
    """§2.7C: re-billed tokens of stale, uncleared tool_result regions.

    Cross-references detector 3 (STALE_TOOL_RESULT): a tool_result block that
    is re-billed (same content_hash across turns) AND is stale (no later edit
    depends on it) contributes its re-billed token volume to the
    ``REBILLING_WASTE`` hook.
    """
    if not regions:
        return 0
    stale_hashes = {
        r.content_hash
        for r in regions
        if r.region == "tool_result" and _is_stale(events, r) and r.content_hash
    }
    if not stale_hashes:
        return 0
    total = 0
    for r in regions:
        if r.region != "tool_result" or not r.content_hash:
            continue
        if r.content_hash in stale_hashes and r.first_turn < r.last_seen_turn:
            total += r.tokens
    return total


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------


def _dup_regions(regions: list[RegionRow], price: float) -> list[Finding]:
    """DUPLICATE: same content_hash re-sent verbatim across turns."""
    by_hash: dict[str, list[RegionRow]] = defaultdict(list)
    for r in regions:
        if r.content_hash:
            by_hash[r.content_hash].append(r)
    findings: list[Finding] = []
    for rows in by_hash.values():
        if len(rows) < 2:
            continue
        span = max(r.last_seen_turn for r in rows) - min(r.first_turn for r in rows)
        if span + 1 < _DUPLICATE_TURNS:
            continue
        rebilled = sum(r.tokens for r in rows) - rows[0].tokens
        region = rows[0].region
        findings.append(
            Finding(
                type="DUPLICATE",
                severity="high" if rebilled > 2000 else "medium",
                tokens=rebilled,
                cost_usd=round(rebilled * price, 6) if price else 0.0,
                fix=_fix_for(region),
                detail={
                    "region": region,
                    "turns_seen": len(rows),
                    "span_turns": span + 1,
                    "content_hash": rows[0].content_hash,
                },
            )
        )
    return findings


def _near_duplicate(
    events: list[dict[str, Any]],
    regions: list[RegionRow],
    price: float,
) -> list[Finding]:
    """NEAR_DUPLICATE: Jaccard >0.85 between distinct content blocks."""
    blocks = _region_blocks(events, regions)
    return detect_near_duplicate_from_text(blocks, price)


def detect_near_duplicate_from_text(
    blocks: list[tuple[str, str, int]],
    price: float,
) -> list[Finding]:
    """NEAR_DUPLICATE using actual block text.

    ``blocks`` is a list of ``(region, text, tokens)``. Returns findings for any
    pair of distinct blocks with Jaccard >0.85.
    """
    findings: list[Finding] = []
    for i, (region_a, text_a, tok_a) in enumerate(blocks):
        set_a = _token_set(text_a)
        if not set_a:
            continue
        for j in range(i + 1, len(blocks)):
            region_b, text_b, tok_b = blocks[j]
            if region_a == region_b and text_a == text_b:
                continue
            set_b = _token_set(text_b)
            if not set_b:
                continue
            union = set_a | set_b
            jacc = len(set_a & set_b) / len(union)
            if jacc > _NEAR_DUP_THRESHOLD:
                wasted = min(tok_a, tok_b)
                findings.append(
                    Finding(
                        type="NEAR_DUPLICATE",
                        severity="medium",
                        tokens=wasted,
                        cost_usd=round(wasted * price, 6) if price else 0.0,
                        fix="deduplicate near-identical context blocks before re-sending",
                        detail={
                            "regions": [region_a, region_b],
                            "jaccard": round(jacc, 3),
                        },
                    )
                )
    return findings


def _stale_tool_result(
    events: list[dict[str, Any]],
    regions: list[RegionRow],
    price: float,
) -> list[Finding]:
    """STALE_TOOL_RESULT: tool output never referenced later, still in window."""
    findings: list[Finding] = []
    seen_hashes: set[str] = set()
    for r in regions:
        if r.region != "tool_result" or not r.content_hash:
            continue
        if r.content_hash in seen_hashes:
            continue
        if not _is_stale(events, r):
            continue
        seen_hashes.add(r.content_hash)
        findings.append(
            Finding(
                type="STALE_TOOL_RESULT",
                severity="medium",
                tokens=r.tokens,
                cost_usd=round(r.tokens * price, 6) if price else 0.0,
                fix="clear stale tool results from the context window once consumed",
                detail={
                    "first_turn": r.first_turn,
                    "last_seen_turn": r.last_seen_turn,
                    "content_hash": r.content_hash,
                },
            )
        )
    return findings


def _unused_tool_schema(
    events: list[dict[str, Any]],
    regions: list[RegionRow],
    price: float,
) -> list[Finding]:
    """UNUSED_TOOL_SCHEMA: a tool schema block re-sent every turn but rarely used."""
    turn_count = max((r.last_seen_turn for r in regions), default=0)
    if turn_count < 3:
        return []
    tool_use_turns: dict[str, set[int]] = defaultdict(set)
    turn_idx = 0
    for e in events:
        if e.get("type") == "user_prompt":
            turn_idx += 1
        if e.get("type") == "tool_call" and e.get("tool_norm_name"):
            tool_use_turns[str(e["tool_norm_name"])].add(turn_idx)
    from cairn.profile.decompose import TOOL_SCHEMA_TOKENS

    findings: list[Finding] = []
    for tool, turns_used in tool_use_turns.items():
        use_fraction = len(turns_used) / max(1, turn_count)
        if use_fraction <= _RARE_USE_FRACTION:
            wasted = TOOL_SCHEMA_TOKENS * (turn_count - len(turns_used))
            findings.append(
                Finding(
                    type="UNUSED_TOOL_SCHEMA",
                    severity="low",
                    tokens=wasted,
                    cost_usd=round(wasted * price, 6) if price else 0.0,
                    fix=f"drop the {tool} tool definition from the schema when not needed",
                    detail={
                        "tool": tool,
                        "used_turns": len(turns_used),
                        "total_turns": turn_count,
                        "use_fraction": round(use_fraction, 3),
                    },
                )
            )
    return findings


def _redundant_fetch(
    events: list[dict[str, Any]],
    regions: list[RegionRow],
    price: float,
) -> list[Finding]:
    """REDUNDANT_RETRIEVAL: retrieved chunk with <15% overlap with model output."""
    output_text = " ".join(
        str(e.get("text_inline") or "") for e in events if e.get("type") == "assistant_message"
    )
    output_set = _token_set(output_text)
    if not output_set:
        return []
    fetched_text = _retrieved_text(events)
    fetched_set = _token_set(fetched_text)
    if not fetched_set:
        return []
    overlap = len(fetched_set & output_set) / len(fetched_set)
    findings: list[Finding] = []
    if overlap < _REDUNDANT_OVERLAP:
        for r in regions:
            if r.region == "retrieved":
                findings.append(
                    Finding(
                        type="REDUNDANT_RETRIEVAL",
                        severity="medium",
                        tokens=r.tokens,
                        cost_usd=round(r.tokens * price, 6) if price else 0.0,
                        fix="skip retrieval that does not feed the model output",
                        detail={
                            "overlap": round(overlap, 3),
                            "content_hash": r.content_hash,
                        },
                    )
                )
                break
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_stale(events: list[dict[str, Any]], region: RegionRow) -> bool:
    """A tool_result region is stale if it persisted >=3 turns with no later edit
    to a path it produced."""
    if region.last_seen_turn - region.first_turn + 1 < _STALE_TURNS:
        return False
    result_paths = {
        str(e["path_rel"]) for e in events if e.get("type") == "tool_result" and e.get("path_rel")
    }
    if not result_paths:
        return True
    for path in result_paths:
        later_edit = any(
            e.get("type") == "tool_call"
            and e.get("tool_norm_name") == "edit"
            and e.get("path_rel") == path
            for e in events
        )
        if not later_edit:
            return True
    return False


def _retrieved_text(events: list[dict[str, Any]]) -> str:
    return "\n".join(
        str(e.get("text_inline") or "")
        for e in events
        if e.get("type") == "tool_result" and e.get("tool_norm_name") in _RETRIEVE_NORMS
    )


def _region_blocks(
    events: list[dict[str, Any]],
    regions: list[RegionRow],
) -> list[tuple[str, str, int]]:
    """Reconstruct (region, text, tokens) blocks for near-duplicate comparison."""
    blocks: list[tuple[str, str, int]] = []
    for region_name in ("tool_result", "retrieved", "assistant_history", "user"):
        texts: list[str] = []
        for e in events:
            if (
                region_name == "tool_result"
                and e.get("type") == "tool_result"
                and e.get("tool_norm_name") not in _RETRIEVE_NORMS
                or region_name == "retrieved"
                and e.get("type") == "tool_result"
                and e.get("tool_norm_name") in _RETRIEVE_NORMS
                or region_name == "assistant_history"
                and e.get("type") == "assistant_message"
                or region_name == "user"
                and e.get("type") == "user_prompt"
            ):
                texts.append(str(e.get("text_inline") or ""))
        text = "\n".join(t for t in texts if t)
        if text:
            blocks.append((region_name, text, _text_tokens(text)))
    return blocks


def _token_set(text: str) -> set[str]:
    return {m.group(0).lower() for m in _WORD_RE.finditer(text)}


def _fix_for(region: str) -> str:
    if region == "tool_result":
        return "clear consumed tool results from the context window"
    if region == "assistant_history":
        return "summarize old assistant turns instead of re-sending verbatim"
    if region == "tool_schema":
        return "drop unused tool definitions from the schema"
    if region == "system":
        return "cache the static system prompt (prefix caching)"
    return "deduplicate re-sent context blocks"
