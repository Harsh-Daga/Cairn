"""Behavioral fingerprint view + AMDM support."""

from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np

from server.analyze.events import spans_to_events
from server.analyze.fingerprint_math import (
    DriftResult,
    detect_drift,
    detect_gradual_drift,
    fingerprint_distance,
    pca_reduce,
)
from server.analyze.views import IncrementalView, trace_input_hash
from server.analyze.waste import compute_waste
from server.models.fingerprint import Fingerprint, FingerprintBaseline
from server.store.repos.fingerprints import FingerprintRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo

VECTOR_DIM = 24
_DEFAULT_WINDOW = 200_000
_BASELINE_MIN_SAMPLES = 4

FINGERPRINT_AXIS_LABELS = [
    "read",
    "edit",
    "bash",
    "search",
    "delete",
    "sub_agent",
    "read/write",
    "explore/exec",
    "retry",
    "error",
    "identical",
    "ctx mean",
    "ctx max",
    "ctx slope",
    "ctx final",
    "turns",
    "entropy",
    "reasoning",
    "avg tokens",
    "out/in",
    "duration",
    "sub count",
]


@dataclass
class FingerprintResult:
    vector: list[float]
    read_write_ratio: float
    exploration_ratio: float
    retry_rate: float
    context_fill_traj: list[float]
    turn_count: int
    tool_entropy: float
    week: str | None
    data_notes: list[str] = field(default_factory=list)


def fingerprint_session(
    events: list[dict[str, Any]],
    *,
    started_at: str | None = None,
    ended_at: str | None = None,
    context_window: int | None = None,
    reasoning_tokens: int = 0,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
) -> FingerprintResult:
    """Compute a 24-dim behavioral fingerprint for one session."""
    tool_calls = [event for event in events if event.get("type") == "tool_call"]
    tool_call_count = len(tool_calls)
    norm_counts: dict[str, int] = defaultdict(int)
    for event in tool_calls:
        name = event.get("tool_norm_name")
        if name:
            norm_counts[str(name)] += 1

    mix_order = ("read", "edit", "bash", "search", "delete", "sub_agent")
    base = max(1, tool_call_count)
    mix = [norm_counts.get(name, 0) / base for name in mix_order]

    read_count = norm_counts.get("read", 0)
    write_count = norm_counts.get("edit", 0) + norm_counts.get("delete", 0)
    explore_count = norm_counts.get("read", 0) + norm_counts.get("search", 0)
    exec_count = (
        norm_counts.get("edit", 0) + norm_counts.get("delete", 0) + norm_counts.get("bash", 0)
    )

    read_write_ratio = read_count / max(1, write_count)
    exploration_ratio = explore_count / max(1, exec_count)

    waste = compute_waste(events, has_cost=False, peak_context_pct=None)
    retry_tokens = sum(
        1 for _, category, _ in waste.tags if category in {"retry_loop", "blind_retry"}
    )
    identical_tokens = sum(1 for _, category, _ in waste.tags if category == "identical_call")
    retry_rate = retry_tokens / base
    identical_rate = identical_tokens / base

    error_count = sum(1 for event in tool_calls if event.get("tool_is_error"))
    error_rate = error_count / base

    window = context_window or _DEFAULT_WINDOW
    context_pct = _context_trajectory(events, window)
    if context_pct:
        mean_ctx = float(np.mean(context_pct))
        max_ctx = float(max(context_pct))
        slope = _linear_slope(context_pct)
        final_ctx = float(context_pct[-1])
    else:
        mean_ctx = 0.0
        max_ctx = 0.0
        slope = 0.0
        final_ctx = 0.0

    turn_count = _count_turns(events)
    turn_log = math.log2(turn_count + 1) / 10.0
    tool_entropy = _shannon_entropy(list(norm_counts.values()))

    total_tokens = total_input_tokens + total_output_tokens
    reasoning_depth = reasoning_tokens / max(1, total_tokens)
    average_tokens_turn = total_tokens / max(1, turn_count)
    average_tokens_norm = min(1.0, average_tokens_turn / 10_000.0)

    out_in_ratio = total_output_tokens / max(1, total_input_tokens)
    out_in_norm = min(1.0, out_in_ratio / 4.0)

    duration_bucket = _duration_bucket(started_at, ended_at)
    subagent_count = norm_counts.get("sub_agent", 0)
    subagent_log = math.log2(subagent_count + 1) / 4.0

    computed = [
        *_clamp(mix, 1.0),
        min(1.0, read_write_ratio / 10.0),
        min(1.0, exploration_ratio / 10.0),
        min(1.0, retry_rate),
        min(1.0, error_rate),
        min(1.0, identical_rate),
        min(1.0, mean_ctx / 100.0),
        min(1.0, max_ctx / 100.0),
        _clamp_slope(slope),
        min(1.0, final_ctx / 100.0),
        min(1.0, turn_log),
        min(1.0, tool_entropy),
        min(1.0, reasoning_depth),
        average_tokens_norm,
        out_in_norm,
        duration_bucket / 2.0,
        min(1.0, subagent_log),
    ]
    vector = computed + [0.0] * (VECTOR_DIM - len(computed))
    week = _iso_week(started_at) if started_at else None

    notes: list[str] = []
    if tool_call_count == 0:
        notes.append("no tool calls: fingerprint is all-zero (vector still emitted)")
    if not context_pct:
        notes.append("no context_tokens_after: trajectory dims are 0")
    return FingerprintResult(
        vector=vector,
        read_write_ratio=round(read_write_ratio, 4),
        exploration_ratio=round(exploration_ratio, 4),
        retry_rate=round(retry_rate, 4),
        context_fill_traj=[round(value, 2) for value in context_pct],
        turn_count=turn_count,
        tool_entropy=round(tool_entropy, 4),
        week=week,
        data_notes=notes,
    )


class FingerprintView(IncrementalView):
    """Compute and persist trace fingerprints and weekly baselines."""

    view_name = "fingerprint"
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
        events = spans_to_events(spans)
        result = fingerprint_session(
            events,
            started_at=trace.started_at,
            ended_at=trace.ended_at,
            context_window=trace.context_window,
            reasoning_tokens=trace.reasoning_tokens,
            total_input_tokens=trace.input_tokens,
            total_output_tokens=trace.output_tokens,
        )
        FingerprintRepo.upsert(
            conn,
            Fingerprint(
                trace_id=trace.trace_id,
                project=trace.project,
                model=trace.model,
                source=trace.source,
                week=result.week,
                ts=trace.started_at,
                vector=result.vector,
                read_write_ratio=result.read_write_ratio,
                exploration_ratio=result.exploration_ratio,
                retry_rate=result.retry_rate,
                tool_entropy=result.tool_entropy,
                turn_count=result.turn_count,
                context_fill_traj=result.context_fill_traj,
            ),
        )
        _update_weekly_baseline(conn, trace.project, trace.model, result.week)


def _update_weekly_baseline(
    conn: sqlite3.Connection,
    project: str | None,
    model: str | None,
    week: str | None,
) -> None:
    if not project or not model or not week:
        return
    rows = conn.execute(
        """
        SELECT vector_json
        FROM fingerprints
        WHERE project = ? AND model = ? AND week = ?
        """,
        (project, model, week),
    ).fetchall()
    vectors = [_decode_vector(row["vector_json"]) for row in rows]
    vectors = [vector for vector in vectors if vector]
    if len(vectors) < _BASELINE_MIN_SAMPLES:
        return
    mean_vector, components, d_eff = pca_reduce(vectors)
    reduced = (np.array(vectors, dtype=float) - mean_vector) @ components.T
    cov = np.cov(reduced, rowvar=False)
    cov_inv = np.linalg.pinv(cov)
    FingerprintRepo.upsert_baseline(
        conn,
        FingerprintBaseline(
            project=project,
            model=model,
            week=week,
            mean_vector=mean_vector.tolist(),
            cov_inv=cov_inv.tolist(),
            n=len(vectors),
        ),
    )
    packed = {"d_eff": d_eff, "components": components.tolist(), "cov_inv": cov_inv.tolist()}
    conn.execute(
        """
        UPDATE fingerprint_baselines
        SET cov_inv_json = ?
        WHERE project = ? AND model = ? AND week = ?
        """,
        (json.dumps(packed), project, model, week),
    )


def _decode_vector(raw: str | None) -> list[float]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [float(value) for value in parsed]


def _clamp(values: list[float], hi: float) -> list[float]:
    return [max(0.0, min(hi, float(value))) for value in values]


def _clamp_slope(slope: float) -> float:
    return max(0.0, min(1.0, (slope + 10.0) / 20.0))


def _context_trajectory(events: list[dict[str, Any]], window: int) -> list[float]:
    pct: list[float] = []
    for event in events:
        context = event.get("context_tokens_after")
        if isinstance(context, (int, float)) and int(context) > 0 and window > 0:
            pct.append(round(int(context) / window * 100, 2))
    return pct


def _count_turns(events: list[dict[str, Any]]) -> int:
    count = sum(1 for event in events if event.get("type") == "user_prompt")
    return max(1, count)


def _shannon_entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = 0.0
    for count in counts:
        if count <= 0:
            continue
        p = count / total
        entropy -= p * math.log2(p)
    return entropy / math.log2(max(2, len(counts)))


def _duration_bucket(started_at: str | None, ended_at: str | None) -> int:
    if not started_at or not ended_at:
        return 0
    start = _parse_iso(started_at)
    end = _parse_iso(ended_at)
    if start is None or end is None:
        return 0
    minutes = (end - start).total_seconds() / 60.0
    if minutes < 0:
        return 0
    if minutes < 5:
        return 0
    if minutes < 30:
        return 1
    return 2


def _parse_iso(timestamp: str) -> datetime | None:
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _iso_week(started_at: str | None) -> str | None:
    if not started_at:
        return None
    day = started_at[:10]
    try:
        year, month, day_of_month = (int(value) for value in day.split("-"))
        iso = date(year, month, day_of_month).isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except (ValueError, OSError):
        return None


def _linear_slope(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    xs = list(range(count))
    mean_x = sum(xs) / count
    mean_y = sum(values) / count
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values, strict=False))
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return numerator / denominator


__all__ = [
    "DriftResult",
    "FINGERPRINT_AXIS_LABELS",
    "FingerprintResult",
    "FingerprintView",
    "VECTOR_DIM",
    "detect_drift",
    "detect_gradual_drift",
    "fingerprint_distance",
    "fingerprint_session",
]
