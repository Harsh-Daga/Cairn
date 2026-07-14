"""Duplicate tool call detector."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from server.improve.detectors._types import (
    FixPayload,
    Insight,
    LiveDetection,
    _cap_savings,
    _data_note,
    _weekly_spend,
)


def detect_live_identical_calls(spans: list[dict[str, Any]]) -> LiveDetection | None:
    """Detect repeated tool calls with the exact same recorded argument hash."""
    signatures: dict[tuple[str, str], list[int]] = defaultdict(list)
    for span in spans:
        if span.get("kind") != "tool_call":
            continue
        name = str(span.get("name") or "tool")
        args_hash = span.get("args_hash") or span.get("text_hash")
        if args_hash:
            signatures[(name, str(args_hash))].append(int(span.get("seq") or 0))
    if not signatures:
        return None
    (name, _args_hash), seqs = max(signatures.items(), key=lambda item: len(item[1]))
    if len(seqs) < 2:
        return None
    return LiveDetection(
        pattern="identical_calls",
        count=len(seqs),
        first_seen_seq=min(seqs),
        advice=(
            f"You've called {name} {len(seqs)}× with identical arguments — reuse the earlier "
            "result unless the underlying input changed."
        ),
        priority=30,
    )


def rule_identical_tool_calls(ctx: dict[str, Any]) -> Insight | None:
    waste = int(ctx.get("identical_call_tokens", 0))
    if waste <= 10_000:
        return None
    total_tokens = int(ctx.get("total_tokens", 0))
    total_cost = float(ctx.get("total_cost", 0))
    days = int(ctx.get("days", 14))
    has_cost = ctx.get("has_cost_sessions", 0) > 0
    savings: float | None = None
    evidence: dict[str, Any] = {
        "waste_tokens": waste,
        "events": int(ctx.get("identical_call_events", 0)),
    }
    if has_cost and total_tokens > 0 and total_cost > 0:
        weekly_spend = _weekly_spend(total_cost, days=days)
        raw = (waste / total_tokens) * weekly_spend * 0.5
        savings = _cap_savings(raw, weekly_spend)
    else:
        evidence.update(_data_note("no cost data: savings estimate unavailable (div0 guard)"))
    return Insight(
        id="identical-tool-calls",
        severity="warning",
        title="Duplicate tool calls",
        body=(
            f"{evidence['events']} duplicate tool calls detected in last {days} days. "
            "Agent is repeating reads/searches it already has results for."
        ),
        evidence=evidence,
        savings_estimate=savings,
        savings_unavailable_reason="No reliable cost data is available for the affected sessions.",
        fix=FixPayload(
            kind="instruction",
            label="Copy duplicate-call rule",
            value=(
                "Reuse an earlier tool result when the tool arguments and underlying file or "
                "input have not changed."
            ),
        ),
        action="cairn optimize",
    )
