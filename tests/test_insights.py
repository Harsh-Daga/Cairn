"""Phase 5 detector and lifecycle tests."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from server.improve.engine import evaluate
from server.improve.evidence import InsightDraft
from server.improve.lifecycle import set_state, upsert_insight
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.insights import InsightRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid


def _now() -> str:
    return datetime.now(UTC).isoformat()


@pytest.fixture
def db(tmp_path: Path) -> tuple[Database, str]:
    database = Database(tmp_path / "cairn.db")
    ws_id = new_ulid()
    WorkspaceRepo.create(
        database.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(tmp_path),
            name="test",
            created_at=_now(),
        ),
    )
    database.reader.commit()
    return database, ws_id


def _insert_trace(
    conn: sqlite3.Connection,
    trace_id: str,
    workspace_id: str,
    *,
    peak: float | None = None,
    input_tokens: int = 100_000,
    cost: float = 5.0,
) -> None:
    conn.execute(
        """
        INSERT INTO traces (
          trace_id, workspace_id, source, external_id, started_at, status,
          input_tokens, output_tokens, cost, cost_source, peak_context_pct, model
        ) VALUES (?, ?, 'claude_code', ?, ?, 'completed', ?, 20000, ?, 'observed', ?, 'claude-opus')
        """,
        (trace_id, workspace_id, trace_id, _now(), input_tokens, cost, peak),
    )


def test_context_pressure_detector(db: tuple[Database, str]) -> None:
    database, ws_id = db
    _insert_trace(database.reader, "t1", ws_id, peak=90.0)
    database.reader.commit()

    insights = evaluate(database.reader, workspace_id=ws_id, days=14)
    ids = {i.detector for i in insights}
    assert "context-window-pressure" in ids
    hit = next(i for i in insights if i.detector == "context-window-pressure")
    assert hit.severity == "error"


def test_identical_calls_detector(db: tuple[Database, str]) -> None:
    database, ws_id = db
    _insert_trace(database.reader, "t2", ws_id)
    conn = database.reader
    for seq in (1, 2, 3):
        conn.execute(
            """
            INSERT INTO spans (
              span_id, trace_id, seq, kind, name, status,
              waste_category, waste_tokens, args_hash
            ) VALUES (?, 't2', ?, 'tool_call', 'read', 'ok', 'identical_call', 5000, 'abc')
            """,
            (f"span{seq}", seq),
        )
    conn.commit()

    insights = evaluate(conn, workspace_id=ws_id, days=14)
    detectors = {i.detector for i in insights}
    assert detectors & {"identical-tool-calls", "retry-storm"}


def test_error_streak_detector(db: tuple[Database, str]) -> None:
    database, ws_id = db
    _insert_trace(database.reader, "t-err", ws_id)
    conn = database.reader
    for seq in range(1, 6):
        conn.execute(
            """
            INSERT INTO spans (span_id, trace_id, seq, kind, name, status)
            VALUES (?, 't-err', ?, 'tool_call', 'run', 'error')
            """,
            (f"e{seq}", seq),
        )
    conn.commit()
    insights = evaluate(conn, workspace_id=ws_id, days=14)
    detectors = {i.detector for i in insights}
    assert detectors & {"error-streak", "retry-storm"}


def test_failing_command_detector(db: tuple[Database, str]) -> None:
    database, ws_id = db
    _insert_trace(database.reader, "t-fail", ws_id)
    conn = database.reader
    for seq in range(1, 4):
        conn.execute(
            """
            INSERT INTO spans (span_id, trace_id, seq, kind, name, status)
            VALUES (?, 't-fail', ?, 'tool_call', 'pytest', 'error')
            """,
            (f"f{seq}", seq),
        )
    conn.commit()
    insights = evaluate(conn, workspace_id=ws_id, days=14)
    detectors = {i.detector for i in insights}
    assert detectors & {"failing-command", "retry-storm"}


def test_reread_hotspot_detector(db: tuple[Database, str]) -> None:
    database, ws_id = db
    _insert_trace(database.reader, "t-reread", ws_id)
    conn = database.reader
    for seq in range(1, 4):
        conn.execute(
            """
            INSERT INTO spans (
              span_id, trace_id, seq, kind, name, status, path_rel, text_hash
            ) VALUES (?, 't-reread', ?, 'tool_call', 'read', 'ok', 'src/a.py', 'hash1')
            """,
            (f"r{seq}", seq),
        )
    conn.commit()
    insights = evaluate(conn, workspace_id=ws_id, days=14)
    detectors = {i.detector for i in insights}
    assert detectors & {"reread-hotspot", "context-thrash"}


def test_stale_tool_results_detector(db: tuple[Database, str]) -> None:
    database, ws_id = db
    _insert_trace(database.reader, "t-stale", ws_id, input_tokens=50_000, cost=10.0)
    conn = database.reader
    for seq in range(1, 4):
        conn.execute(
            """
            INSERT INTO spans (
              span_id, trace_id, seq, kind, name, status,
              waste_category, waste_tokens
            ) VALUES (?, 't-stale', ?, 'tool_result', 'read', 'ok', 'stale_context', 8000)
            """,
            (f"s{seq}", seq),
        )
    conn.commit()
    insights = evaluate(conn, workspace_id=ws_id, days=14)
    detectors = {i.detector for i in insights}
    assert detectors & {"stale-tool-results", "context-thrash"}


def test_cost_anomaly_detector(db: tuple[Database, str]) -> None:
    database, ws_id = db
    conn = database.reader
    for i in range(21):
        conn.execute(
            """
            INSERT INTO traces (
              trace_id, workspace_id, source, external_id, started_at, status,
              input_tokens, output_tokens, cost, cost_source, difficulty, model
            ) VALUES (
              ?, ?, 'claude_code', ?, ?, 'completed',
              10000, 2000, ?, 'observed', 'medium', 'claude-opus'
            )
            """,
            (f"t-cost-{i}", ws_id, f"t-cost-{i}", _now(), 5.0 + i * 0.01),
        )
    conn.execute(
        """
        INSERT INTO traces (
          trace_id, workspace_id, source, external_id, started_at, status,
          input_tokens, output_tokens, cost, cost_source, difficulty, model
        ) VALUES (
          't-outlier', ?, 'claude_code', 't-outlier', ?, 'completed',
          10000, 2000, 99.0, 'observed', 'medium', 'claude-opus'
        )
        """,
        (ws_id, _now()),
    )
    conn.commit()
    insights = evaluate(conn, workspace_id=ws_id, days=14)
    assert any(i.detector == "cost-anomaly" for i in insights)


def test_lifecycle_ack_to_fixed(db: tuple[Database, str]) -> None:
    database, ws_id = db
    draft = InsightDraft(
        fingerprint="test-rule",
        detector="test-rule",
        detector_version=1,
        severity="warning",
        title="Test",
        body="Body",
        trace_ids=["t1"],
    )
    insight = upsert_insight(database.reader, draft)
    database.reader.commit()
    set_state(database.reader, insight.insight_id, "ack", changed_by="user")
    database.reader.commit()

    old = (datetime.now(UTC) - timedelta(days=15)).isoformat()
    database.reader.execute(
        "UPDATE insights SET last_seen_at = ? WHERE insight_id = ?",
        (old, insight.insight_id),
    )
    database.reader.commit()

    evaluate(database.reader, workspace_id=ws_id, days=14)
    state = InsightRepo.get_state(database.reader, insight.insight_id)
    assert state is not None
    assert state.state == "fixed"


def test_lifecycle_regression_reopens(db: tuple[Database, str]) -> None:
    database, ws_id = db
    draft = InsightDraft(
        fingerprint="retry-loop",
        detector="retry-loop",
        detector_version=1,
        severity="warning",
        title="Retry",
        body="Body",
    )
    insight = upsert_insight(database.reader, draft)
    set_state(database.reader, insight.insight_id, "fixed")
    database.reader.commit()

    upsert_insight(database.reader, draft)
    database.reader.commit()
    state = InsightRepo.get_state(database.reader, insight.insight_id)
    assert state is not None
    assert state.state == "regressed"


def test_evidence_resolves_trace_ids(db: tuple[Database, str]) -> None:
    database, ws_id = db
    _insert_trace(database.reader, "trace-abc", ws_id, peak=92.0)
    database.reader.commit()
    insights = evaluate(database.reader, workspace_id=ws_id, days=14)
    assert insights
    from server.store.repos.evidence import EvidenceRepo

    ev = EvidenceRepo.get(database.reader, insights[0].evidence_id)
    assert ev is not None
    assert ev.trace_ids
