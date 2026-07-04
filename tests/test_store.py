"""Phase 1 store tests — migration, repos, survival."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from server.models import (
    Actor,
    Annotation,
    ContextRegion,
    DataQuality,
    Diagnostic,
    Evidence,
    Experiment,
    Fingerprint,
    FingerprintBaseline,
    IngestCursor,
    Insight,
    InsightState,
    Outcome,
    RollupDaily,
    Span,
    Trace,
    ViewState,
    Workspace,
)
from server.store.db import Database, connect
from server.store.migrate import migrate
from server.store.repos import (
    ActorRepo,
    AnnotationRepo,
    DataQualityRepo,
    DiagnosticRepo,
    EvidenceRepo,
    ExperimentRepo,
    FingerprintRepo,
    IngestCursorRepo,
    InsightRepo,
    OutcomeRepo,
    RollupRepo,
    SpanRepo,
    TraceListFilters,
    TraceRepo,
    ViewStateRepo,
    WorkspaceRepo,
)
from server.util.ids import new_ulid

NOW = datetime.now(UTC).isoformat()


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    db_path = tmp_path / "test.db"
    connection = connect(db_path)
    migrate(connection)
    yield connection
    connection.close()


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "writer.db")
    yield database
    database.close()


def test_migration_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "migrate.db"
    connection = connect(db_path)
    first = migrate(connection)
    second = migrate(connection)
    assert "0001_init" in first
    assert second == []
    connection.close()


def test_all_tables_exist(conn: sqlite3.Connection) -> None:
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    }
    expected = {
        "_migrations",
        "actors",
        "annotations",
        "context_regions",
        "data_quality",
        "diagnostics",
        "evidence",
        "experiments",
        "fingerprint_baselines",
        "fingerprints",
        "ingest_cursors",
        "insight_states",
        "insights",
        "outcomes",
        "rollup_daily",
        "span_links",
        "spans",
        "spans_fts",
        "traces",
        "view_state",
        "workspaces",
    }
    assert expected.issubset(tables)


def test_survival_experiment_outcome(conn: sqlite3.Connection) -> None:
    ws_id = new_ulid()
    WorkspaceRepo.create(
        conn,
        Workspace(workspace_id=ws_id, root_path="/tmp/proj", name="proj", created_at=NOW),
    )
    trace_id = new_ulid()
    TraceRepo.create(
        conn,
        Trace(trace_id=trace_id, workspace_id=ws_id, source="claude_code", started_at=NOW),
    )
    ev_id = new_ulid()
    EvidenceRepo.create(
        conn,
        Evidence(
            evidence_id=ev_id,
            producer="detector:test@1",
            produced_at=NOW,
            trace_ids=[trace_id],
            metrics={"count": 3},
        ),
    )
    exp_id = new_ulid()
    ExperimentRepo.create(
        conn,
        Experiment(
            experiment_id=exp_id,
            created_at=NOW,
            target_file="AGENTS.md",
            block_key="rule-1",
            kind="rule",
            content="Be concise.",
            evidence_id=ev_id,
            status="proposed",
            min_holdout=8,
            confound_flag=False,
        ),
    )
    OutcomeRepo.create(
        conn,
        Outcome(trace_id=trace_id, quality_score=72.0, captured_at=NOW),
    )
    conn.commit()

    migrate(conn)

    assert ExperimentRepo.get(conn, exp_id) is not None
    assert OutcomeRepo.get(conn, trace_id) is not None


def test_workspace_round_trip(conn: sqlite3.Connection) -> None:
    ws = Workspace(workspace_id=new_ulid(), root_path="/a", name="A", created_at=NOW)
    WorkspaceRepo.create(conn, ws)
    got = WorkspaceRepo.get(conn, ws.workspace_id)
    assert got == ws


def test_actor_round_trip(conn: sqlite3.Connection) -> None:
    actor = Actor(
        actor_id=new_ulid(),
        kind="human",
        display_name="Harsh",
        identity_hint="h@example.com",
    )
    ActorRepo.create(conn, actor)
    got = ActorRepo.get_by_identity(conn, "human", "h@example.com")
    assert got == actor


def test_trace_round_trip(conn: sqlite3.Connection) -> None:
    ws_id = new_ulid()
    WorkspaceRepo.create(
        conn, Workspace(workspace_id=ws_id, root_path="/b", name="B", created_at=NOW)
    )
    trace = Trace(
        trace_id=new_ulid(),
        workspace_id=ws_id,
        source="cursor",
        title="fix bug",
        started_at=NOW,
        input_tokens=100,
        output_tokens=50,
    )
    TraceRepo.create(conn, trace)
    got = TraceRepo.get(conn, trace.trace_id)
    assert got == trace


def test_span_round_trip(conn: sqlite3.Connection) -> None:
    ws_id = new_ulid()
    WorkspaceRepo.create(
        conn, Workspace(workspace_id=ws_id, root_path="/c", name="C", created_at=NOW)
    )
    trace_id = new_ulid()
    TraceRepo.create(
        conn, Trace(trace_id=trace_id, workspace_id=ws_id, source="codex", started_at=NOW)
    )
    span = Span(
        span_id=new_ulid(),
        trace_id=trace_id,
        seq=1,
        kind="tool_call",
        name="bash",
        status="ok",
    )
    SpanRepo.create(conn, span)
    spans = SpanRepo.list_by_trace(conn, trace_id)
    assert spans == [span]


def test_insight_round_trip(conn: sqlite3.Connection) -> None:
    ws_id = new_ulid()
    WorkspaceRepo.create(
        conn, Workspace(workspace_id=ws_id, root_path="/d", name="D", created_at=NOW)
    )
    trace_id = new_ulid()
    TraceRepo.create(
        conn, Trace(trace_id=trace_id, workspace_id=ws_id, source="claude_code", started_at=NOW)
    )
    ev_id = new_ulid()
    EvidenceRepo.create(
        conn,
        Evidence(
            evidence_id=ev_id,
            producer="detector:reread@1",
            produced_at=NOW,
            trace_ids=[trace_id],
            metrics={"reads": 5},
        ),
    )
    insight = Insight(
        insight_id=new_ulid(),
        fingerprint="reread-hotspot:src/a.py",
        detector="reread_hotspot",
        detector_version=1,
        severity="warning",
        title="Re-read hotspot",
        body="File re-read 5 times.",
        evidence_id=ev_id,
        created_at=NOW,
        last_seen_at=NOW,
    )
    InsightRepo.create(conn, insight)
    InsightRepo.set_state(
        conn,
        InsightState(insight_id=insight.insight_id, state="ack", changed_at=NOW, changed_by="user"),
    )
    rows = InsightRepo.list_by_state(conn, state="ack")
    assert len(rows) == 1
    assert rows[0].insight.insight_id == insight.insight_id


def test_trace_list_filters(conn: sqlite3.Connection) -> None:
    ws_id = new_ulid()
    WorkspaceRepo.create(
        conn, Workspace(workspace_id=ws_id, root_path="/e", name="E", created_at=NOW)
    )
    actor_id = new_ulid()
    ActorRepo.create(
        conn,
        Actor(actor_id=actor_id, kind="human", display_name="Dev", identity_hint="dev@co"),
    )
    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    old = (datetime.now(UTC) - timedelta(days=40)).isoformat()
    TraceRepo.create(
        conn,
        Trace(
            trace_id=new_ulid(),
            workspace_id=ws_id,
            source="cursor",
            project="app",
            actor_id=actor_id,
            started_at=recent,
        ),
    )
    TraceRepo.create(
        conn,
        Trace(
            trace_id=new_ulid(),
            workspace_id=ws_id,
            source="claude_code",
            project="app",
            started_at=old,
        ),
    )
    rows = TraceRepo.list(
        conn,
        TraceListFilters(days=7, source="cursor", project="app", actor=actor_id, limit=10),
    )
    assert len(rows) == 1
    assert rows[0].source == "cursor"


def test_database_writer_thread(db: Database) -> None:
    ws_id = new_ulid()

    def _insert(connection: sqlite3.Connection) -> str:
        WorkspaceRepo.create(
            connection,
            Workspace(workspace_id=ws_id, root_path="/w", name="W", created_at=NOW),
        )
        return ws_id

    result = db.write(_insert)
    assert result == ws_id
    got = WorkspaceRepo.get(db.reader, ws_id)
    assert got is not None


def test_remaining_tables_round_trip(conn: sqlite3.Connection) -> None:
    ws_id = new_ulid()
    WorkspaceRepo.create(
        conn, Workspace(workspace_id=ws_id, root_path="/f", name="F", created_at=NOW)
    )
    trace_id = new_ulid()
    TraceRepo.create(
        conn, Trace(trace_id=trace_id, workspace_id=ws_id, source="goose", started_at=NOW)
    )
    span_id = new_ulid()
    SpanRepo.create(
        conn,
        Span(span_id=span_id, trace_id=trace_id, seq=1, kind="llm_call", status="ok"),
    )

    region = ContextRegion(span_id=span_id, region="system", tokens=500, cost=0.01)
    conn.execute(
        "INSERT INTO context_regions "
        "(span_id, region, tokens, cost, content_hash, "
        "first_turn, last_seen_turn, still_in_window) "
        "VALUES (?,?,?,?,?,?,?,?)",
        region.to_row(),
    )

    FingerprintRepo.create(
        conn,
        Fingerprint(
            trace_id=trace_id,
            vector=[0.1, 0.2],
            project="app",
            model="gpt-4",
            source="goose",
            week="2026-W01",
            ts=NOW,
        ),
    )
    FingerprintRepo.upsert_baseline(
        conn,
        FingerprintBaseline(
            project="app",
            model="gpt-4",
            week="2026-W01",
            mean_vector=[0.1, 0.2],
            cov_inv=[[1.0, 0.0], [0.0, 1.0]],
            n=10,
        ),
    )
    DiagnosticRepo.create(
        conn,
        Diagnostic(trace_id=trace_id, primary_category="tool_error", computed_at=NOW),
    )
    ev_id = new_ulid()
    EvidenceRepo.create(
        conn,
        Evidence(
            evidence_id=ev_id,
            producer="usage@1",
            produced_at=NOW,
            trace_ids=[trace_id],
            metrics={"tokens": 100},
        ),
    )
    ViewStateRepo.upsert(
        conn,
        ViewState(
            view="usage",
            key=trace_id,
            version=1,
            input_hash="abc",
            computed_at=NOW,
        ),
    )
    RollupRepo.upsert(
        conn,
        RollupDaily(
            day="2026-01-01",
            workspace_id=ws_id,
            project="app",
            source="goose",
            traces=1,
            input_tokens=100,
        ),
    )
    DataQualityRepo.create(
        conn,
        DataQuality(trace_id=trace_id, pct_tokens_measured=0.9, computed_at=NOW),
    )
    IngestCursorRepo.upsert(
        conn,
        IngestCursor(source="cursor", stream="main", cursor={"offset": 42}, updated_at=NOW),
    )
    AnnotationRepo.create(
        conn,
        Annotation(
            annotation_id=new_ulid(),
            subject_type="trace",
            subject_id=trace_id,
            body="note",
            created_at=NOW,
        ),
    )
    conn.commit()

    assert FingerprintRepo.get(conn, trace_id) is not None
    assert DiagnosticRepo.get(conn, trace_id) is not None
    assert ViewStateRepo.get(conn, "usage", trace_id) is not None
    assert len(RollupRepo.list_by_workspace(conn, ws_id)) == 1
    assert DataQualityRepo.get(conn, trace_id) is not None
    assert IngestCursorRepo.list_all(conn)[0].cursor == {"offset": 42}
    assert len(AnnotationRepo.list_by_subject(conn, "trace", trace_id)) == 1
