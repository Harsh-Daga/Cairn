"""Trace turn alignment and delta summaries."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from server.models.span import Span
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo

MAX_DIFF_SPANS_PER_SIDE = 2_000
MAX_LCS_CELLS = 1_000_000


@dataclass(frozen=True)
class _AlignedTurn:
    op: str
    a: Span | None
    b: Span | None


def _turn_key(span: Span) -> tuple[str, str]:
    return (span.kind, span.name or "")


def _span_tokens(span: Span | None) -> int:
    if span is None:
        return 0
    return (span.input_tokens or 0) + (span.output_tokens or 0)


def _span_quality(span: Span | None) -> float:
    if span is None:
        return 0.0
    return 1.0 if span.status == "ok" else 0.0


def _trace_quality(spans: list[Span]) -> float:
    if not spans:
        return 0.0
    return sum(_span_quality(span) for span in spans) / len(spans)


def align_turns_lcs(a_spans: list[Span], b_spans: list[Span]) -> list[_AlignedTurn]:
    """Align two turn sequences using LCS over (kind, name)."""
    n = len(a_spans)
    m = len(b_spans)
    if n * m > MAX_LCS_CELLS:
        bounded_out: list[_AlignedTurn] = []
        for index in range(max(n, m)):
            span_a = a_spans[index] if index < n else None
            span_b = b_spans[index] if index < m else None
            if span_a is not None and span_b is not None and _turn_key(span_a) == _turn_key(span_b):
                bounded_out.append(_AlignedTurn(op="match", a=span_a, b=span_b))
            else:
                if span_a is not None:
                    bounded_out.append(_AlignedTurn(op="delete", a=span_a, b=None))
                if span_b is not None:
                    bounded_out.append(_AlignedTurn(op="insert", a=None, b=span_b))
        return bounded_out
    a_keys = [_turn_key(span) for span in a_spans]
    b_keys = [_turn_key(span) for span in b_spans]
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a_keys[i] == b_keys[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])

    out: list[_AlignedTurn] = []
    i = 0
    j = 0
    while i < n and j < m:
        if a_keys[i] == b_keys[j]:
            out.append(_AlignedTurn(op="match", a=a_spans[i], b=b_spans[j]))
            i += 1
            j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            out.append(_AlignedTurn(op="delete", a=a_spans[i], b=None))
            i += 1
        else:
            out.append(_AlignedTurn(op="insert", a=None, b=b_spans[j]))
            j += 1
    while i < n:
        out.append(_AlignedTurn(op="delete", a=a_spans[i], b=None))
        i += 1
    while j < m:
        out.append(_AlignedTurn(op="insert", a=None, b=b_spans[j]))
        j += 1
    return out


def build_trace_diff_payload(
    conn: sqlite3.Connection,
    *,
    trace_id_a: str,
    trace_id_b: str,
) -> dict[str, object] | None:
    trace_a = TraceRepo.get(conn, trace_id_a)
    trace_b = TraceRepo.get(conn, trace_id_b)
    if trace_a is None or trace_b is None:
        return None
    spans_a = SpanRepo.list_by_trace(conn, trace_id_a)
    spans_b = SpanRepo.list_by_trace(conn, trace_id_b)
    aligned = align_turns_lcs(
        spans_a[:MAX_DIFF_SPANS_PER_SIDE],
        spans_b[:MAX_DIFF_SPANS_PER_SIDE],
    )

    turns: list[dict[str, object]] = []
    for idx, item in enumerate(aligned, start=1):
        a_tokens = _span_tokens(item.a)
        b_tokens = _span_tokens(item.b)
        a_waste = item.a.waste_tokens if item.a is not None else 0
        b_waste = item.b.waste_tokens if item.b is not None else 0
        a_quality = _span_quality(item.a)
        b_quality = _span_quality(item.b)
        turns.append(
            {
                "index": idx,
                "op": item.op,
                "a": item.a.model_dump() if item.a is not None else None,
                "b": item.b.model_dump() if item.b is not None else None,
                "delta_tokens": b_tokens - a_tokens,
                "delta_waste_tokens": b_waste - a_waste,
                "delta_quality": b_quality - a_quality,
            }
        )

    quality_a = _trace_quality(spans_a)
    quality_b = _trace_quality(spans_b)
    return {
        "a": trace_a.model_dump(),
        "b": trace_b.model_dump(),
        "summary": {
            "cost_a": trace_a.cost,
            "cost_b": trace_b.cost,
            "delta_cost": trace_b.cost - trace_a.cost,
            "waste_a": trace_a.waste_tokens,
            "waste_b": trace_b.waste_tokens,
            "delta_waste_tokens": trace_b.waste_tokens - trace_a.waste_tokens,
            "quality_a": quality_a,
            "quality_b": quality_b,
            "delta_quality": quality_b - quality_a,
        },
        "turns": turns,
    }
