"""Deterministic, generated-on-demand benchmark ledgers."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from server.store.db import connect
from server.store.migrate import migrate


@dataclass(frozen=True, slots=True)
class BenchmarkProfile:
    name: str
    trace_count: int
    spans_per_trace: int
    wide_trace_spans: int


@dataclass(frozen=True, slots=True)
class BenchmarkLedger:
    path: Path
    profile: BenchmarkProfile
    trace_count: int
    span_count: int
    bytes: int


PROFILES = {
    "small": BenchmarkProfile("small", trace_count=100, spans_per_trace=5, wide_trace_spans=100),
    "medium": BenchmarkProfile(
        "medium",
        trace_count=1_000,
        spans_per_trace=5,
        wide_trace_spans=500,
    ),
    "large": BenchmarkProfile(
        "large",
        trace_count=10_000,
        spans_per_trace=5,
        wide_trace_spans=2_500,
    ),
}
BENCHMARK_WORKSPACE_ID = "benchmark-workspace"
BENCHMARK_ANCHOR = datetime(2026, 7, 18, 12, tzinfo=UTC)
_BATCH_SIZE = 500


def _remove_existing(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("benchmark database path must not be a symlink")
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{path}{suffix}")
        if candidate.exists():
            candidate.unlink()


def _trace_row(index: int, profile: BenchmarkProfile) -> tuple[object, ...]:
    started = BENCHMARK_ANCHOR - timedelta(
        days=(profile.trace_count - index - 1) % 90,
        seconds=(profile.trace_count - index - 1) % 86_400,
    )
    ended = started + timedelta(seconds=30 + index % 600)
    input_tokens = 800 + index % 8_000
    output_tokens = 300 + index % 2_000
    cost = round(input_tokens * 0.000003 + output_tokens * 0.000015, 6)
    return (
        f"bench-trace-{index:06d}",
        BENCHMARK_WORKSPACE_ID,
        ("claude_code", "cursor", "codex", "cline")[index % 4],
        f"bench-session-{index:06d}",
        f"bench-actor-{index % 3}",
        f"project-{index % 20:02d}",
        "/benchmark/workspace",
        ("claude-4.6-sonnet", "gpt-5.5-medium")[index % 2],
        started.isoformat(),
        ended.isoformat(),
        "error" if index % 97 == 0 else "completed",
        f"Benchmark session {index:06d} pytest" if index % 10 == 0 else f"Session {index:06d}",
        input_tokens,
        output_tokens,
        cost,
        "measured",
        profile.wide_trace_spans if index == 0 else profile.spans_per_trace,
        2,
        1 if index % 97 == 0 else 0,
        100 + index % 400,
    )


def _span_rows(index: int, count: int) -> list[tuple[object, ...]]:
    trace_id = f"bench-trace-{index:06d}"
    started = BENCHMARK_ANCHOR - timedelta(days=index % 90, seconds=index % 86_400)
    rows: list[tuple[object, ...]] = []
    for seq in range(count):
        kind = "agent" if seq == 0 else ("tool_call" if seq % 2 else "tool_result")
        span_id = f"bench-span-{index:06d}-{seq:05d}"
        rows.append(
            (
                span_id,
                trace_id,
                None if seq == 0 else f"bench-span-{index:06d}-00000",
                seq + 1,
                kind,
                "pytest" if seq % 11 == 0 else ("read" if seq % 2 else "tool result"),
                f"agent-{index % 8}",
                (started + timedelta(milliseconds=seq * 10)).isoformat(),
                10.0,
                "error" if index % 97 == 0 and seq == count - 1 else "ok",
                40 + seq % 100,
                20 + seq % 50,
                "pytest output" if seq % 11 == 0 else f"bounded benchmark span {seq}",
                "retry_loop" if seq and seq % 23 == 0 else None,
                25 if seq and seq % 23 == 0 else 0,
                json.dumps({"benchmark": True, "seq": seq}, separators=(",", ":")),
            )
        )
    return rows


def _insert_batch(
    conn: sqlite3.Connection,
    profile: BenchmarkProfile,
    start: int,
    end: int,
) -> int:
    trace_rows = [_trace_row(index, profile) for index in range(start, end)]
    conn.executemany(
        """
        INSERT INTO traces (
          trace_id, workspace_id, source, external_id, actor_id, project, cwd, model,
          started_at, ended_at, status, title, input_tokens, output_tokens, cost, cost_source,
          span_count, tool_calls, tool_errors, waste_tokens
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        trace_rows,
    )
    span_count = 0
    for index in range(start, end):
        count = profile.wide_trace_spans if index == 0 else profile.spans_per_trace
        spans = _span_rows(index, count)
        conn.executemany(
            """
            INSERT INTO spans (
              span_id, trace_id, parent_span_id, seq, kind, name, agent_id,
              started_at, duration_ms, status, input_tokens, output_tokens,
              text_inline, waste_category, waste_tokens, attrs_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            spans,
        )
        span_count += len(spans)
        conn.execute(
            """
            INSERT INTO outcomes (
              trace_id, tests_run, tests_passed, tests_failed, build_status,
              quality_score, cost_per_success, outcome_label, label_source, captured_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"bench-trace-{index:06d}",
                20,
                19 if index % 97 == 0 else 20,
                1 if index % 97 == 0 else 0,
                "failed" if index % 97 == 0 else "passed",
                float(50 + index % 51),
                0.01 + (index % 100) / 1_000,
                "failure" if index % 97 == 0 else "success",
                "benchmark",
                BENCHMARK_ANCHOR.isoformat(),
            ),
        )
        conn.execute(
            """
            INSERT INTO context_regions (
              span_id, region, tokens, cost, content_hash, first_turn, last_seen_turn,
              still_in_window
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"bench-span-{index:06d}-00001",
                ("tool_result", "history", "system")[index % 3],
                200 + index % 400,
                0.001,
                f"bench-region-{index:06d}",
                1,
                3,
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO fingerprints (
              trace_id, project, model, source, week, ts, vector_json,
              read_write_ratio, exploration_ratio, retry_rate, tool_entropy,
              turn_count, context_fill_traj_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"bench-trace-{index:06d}",
                f"project-{index % 20:02d}",
                ("claude-4.6-sonnet", "gpt-5.5-medium")[index % 2],
                ("claude_code", "cursor", "codex", "cline")[index % 4],
                f"2026-W{index % 13:02d}",
                BENCHMARK_ANCHOR.isoformat(),
                "[0.2,0.3,0.1,0.4,0.2]",
                0.2,
                0.3,
                0.1,
                0.4,
                count,
                "[20,40,60]",
            ),
        )
    return span_count


def generate_benchmark_ledger(path: Path, profile: BenchmarkProfile) -> BenchmarkLedger:
    """Generate a deterministic benchmark ledger without committing a binary fixture."""
    target = path.expanduser().resolve()
    _remove_existing(target)
    conn = connect(target)
    try:
        migrate(conn)
        workspace_root = target.parent.parent if target.parent.name == ".cairn" else target.parent
        conn.execute(
            """
            INSERT INTO workspaces (workspace_id, root_path, name, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                BENCHMARK_WORKSPACE_ID,
                str(workspace_root),
                f"benchmark-{profile.name}",
                BENCHMARK_ANCHOR.isoformat(),
            ),
        )
        conn.executemany(
            """
            INSERT INTO actors (actor_id, kind, display_name, identity_hint)
            VALUES (?, ?, ?, ?)
            """,
            [
                ("bench-actor-0", "human", "Benchmark Human", "human@benchmark.invalid"),
                ("bench-actor-1", "agent", "Benchmark Agent", "agent@benchmark.invalid"),
                ("bench-actor-2", "service", "Benchmark CI", "ci@benchmark.invalid"),
            ],
        )
        span_count = 0
        for start in range(0, profile.trace_count, _BATCH_SIZE):
            end = min(profile.trace_count, start + _BATCH_SIZE)
            span_count += _insert_batch(conn, profile, start, end)
            conn.commit()
        conn.execute("PRAGMA optimize")
        conn.commit()
    finally:
        conn.close()
    return BenchmarkLedger(
        path=target,
        profile=profile,
        trace_count=profile.trace_count,
        span_count=span_count,
        bytes=target.stat().st_size,
    )
