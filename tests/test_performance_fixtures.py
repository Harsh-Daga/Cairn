"""Stable structural budgets for generated scale fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from server.api.payloads import build_replay_checkpoints, build_trace_detail
from server.store.benchmark import PROFILES, generate_benchmark_ledger
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceListFilters, TraceRepo


@pytest.fixture(scope="module")
def large_ledger(tmp_path_factory: pytest.TempPathFactory) -> Path:
    workspace = tmp_path_factory.mktemp("large-benchmark")
    path = workspace / ".cairn" / "cairn.db"
    generate_benchmark_ledger(path, PROFILES["large"])
    return path


def test_profiles_cover_small_medium_and_ten_thousand_sessions() -> None:
    assert set(PROFILES) == {"small", "medium", "large"}
    assert PROFILES["small"].trace_count == 100
    assert PROFILES["medium"].trace_count == 1_000
    assert PROFILES["large"].trace_count == 10_000
    assert PROFILES["large"].wide_trace_spans >= 2_500


def test_large_fixture_has_bounded_size_and_canonical_scale(large_ledger: Path) -> None:
    with sqlite3.connect(large_ledger) as conn:
        trace_count = int(conn.execute("SELECT COUNT(*) FROM traces").fetchone()[0])
        span_count = int(conn.execute("SELECT COUNT(*) FROM spans").fetchone()[0])
        integrity = str(conn.execute("PRAGMA quick_check").fetchone()[0])

    assert trace_count == 10_000
    assert span_count == 52_495
    assert integrity == "ok"
    assert large_ledger.stat().st_size < 64 * 1024 * 1024


def test_large_fixture_queries_keep_page_and_wide_trace_contracts(
    large_ledger: Path,
) -> None:
    conn = sqlite3.connect(f"file:{large_ledger.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        traces = TraceRepo.list(
            conn,
            TraceListFilters(
                workspace_id="benchmark-workspace",
                source="cursor",
                limit=200,
            ),
        )
        wide_spans = SpanRepo.list_by_trace(conn, "bench-trace-000000")
    finally:
        conn.close()

    assert len(traces) == 200
    assert len(wide_spans) == 2_500


def test_large_trace_payloads_stay_within_structural_size_budgets(
    large_ledger: Path,
) -> None:
    conn = sqlite3.connect(f"file:{large_ledger.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        detail = build_trace_detail(conn, "bench-trace-000000")
        replay = build_replay_checkpoints(conn, "bench-trace-000000")
    finally:
        conn.close()

    assert detail is not None
    assert replay is not None and replay.checkpoints is not None
    assert replay.checkpoints[-1].seq == 2_500
    assert len(replay.checkpoints[-1].spans) == 2_500
    assert len(replay.checkpoints) <= 2
    assert len(detail.model_dump_json().encode()) < 4 * 1024 * 1024
    assert len(replay.model_dump_json().encode()) < 4 * 1024 * 1024


def test_generation_is_logically_repeatable(tmp_path: Path) -> None:
    path = tmp_path / ".cairn" / "cairn.db"
    first = generate_benchmark_ledger(path, PROFILES["small"])
    with sqlite3.connect(path) as conn:
        first_signature = conn.execute(
            """
            SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(waste_tokens)
            FROM traces
            """
        ).fetchone()
    second = generate_benchmark_ledger(path, PROFILES["small"])
    with sqlite3.connect(path) as conn:
        second_signature = conn.execute(
            """
            SELECT COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(waste_tokens)
            FROM traces
            """
        ).fetchone()

    assert first.trace_count == second.trace_count == 100
    assert first.span_count == second.span_count == 595
    assert first_signature == second_signature
