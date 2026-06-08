"""Phase 3 domain model tests."""

from __future__ import annotations

from cairn.ingest.writer import SessionSummary
from cairn.model.artifact import Artifact, FileArtifact, LineageEdge
from cairn.model.session import Session, SessionEvent, session_from_writer_summary
from cairn.model.workflow import ContextSelector, WorkflowDef, WorkflowStep


def test_session_session_key() -> None:
    session = Session(
        run_id="run-1",
        external_id="abc-123",
        source="claude-code",
        status="completed",
        started_at="2026-01-01T00:00:00Z",
        ended_at="2026-01-01T01:00:00Z",
        cwd="/tmp/repo",
        git_branch="main",
        git_commit="deadbeef",
        model="claude-sonnet",
        total_input_tokens=100,
        total_output_tokens=200,
        total_cost=0.05,
        trajectory_hash="hash123",
        event_count=42,
    )
    assert session.session_key == "claude-code:abc-123"
    d = session.to_summary_dict()
    assert d["session_key"] == "claude-code:abc-123"
    assert d["event_count"] == 42


def test_session_from_writer_summary() -> None:
    summary = SessionSummary(
        run_id="r1",
        external_id="ext",
        source="codex",
        cwd=None,
        git_branch="dev",
        git_commit=None,
        started_at="t0",
        ended_at="t1",
        status="completed",
        model="gpt-4",
        total_input_tokens=10,
        total_output_tokens=20,
        total_cost=None,
        trajectory_hash=None,
        event_count=5,
    )
    session = session_from_writer_summary(summary)
    assert session.source == "codex"
    assert session.external_id == "ext"


def test_session_event() -> None:
    event = SessionEvent(
        seq=1,
        event_type="tool_call",
        payload={"name": "Read", "path": "src/main.py"},
        timestamp="2026-01-01T00:01:00Z",
    )
    assert event.event_type == "tool_call"
    assert event.payload["name"] == "Read"


def test_file_artifact_snapshot_quality() -> None:
    exact = FileArtifact("a.py", "before", "after", 1, 2)
    assert exact.snapshot_quality() == "exact"

    partial = FileArtifact("b.py", None, "after", 1, 2)
    assert partial.snapshot_quality() == "partial"

    inferred = FileArtifact("c.py", None, None, 1, 2)
    assert inferred.snapshot_quality() == "inferred"


def test_file_artifact_to_artifact() -> None:
    fa = FileArtifact("src/x.py", "h1", "h2", 0, 5)
    art = fa.to_artifact("run-1", "sess-1")
    assert art.kind == "file"
    assert art.content_hash == "h2"
    assert art.path_rel == "src/x.py"
    assert art.metadata["snapshot_quality"] == "exact"


def test_artifact_to_dict() -> None:
    art = Artifact(
        content_hash="abc",
        kind="report",
        path_rel="outputs/report.md",
        mime="text/markdown",
        run_id="run-1",
        session_id=None,
        size_bytes=1024,
        metadata={"title": "Summary"},
    )
    d = art.to_dict()
    assert d["artifact_id"] == "abc"
    assert d["kind"] == "report"


def test_lineage_edge() -> None:
    edge = LineageEdge("derived_from", "artifact-a", "artifact-b")
    assert edge.relation == "derived_from"
    assert edge.from_id == "artifact-a"


def test_workflow_def_workflow_ref() -> None:
    step = WorkflowStep(
        name="summarize",
        kind="chat",
        prompt="summarize.md",
        output="outputs/summary.md",
        model=None,
        params={},
        materialization="cached",
        samples=1,
        tags=(),
        over=None,
        inputs=None,
        system=None,
    )
    wf = WorkflowDef(
        name="docs",
        version="v1",
        description="Summarize docs",
        status="validated",
        context=ContextSelector(include=("context/**/*.md",)),
        steps={"summarize": step},
    )
    assert wf.workflow_ref == "docs@v1"
    d = wf.to_dict()
    assert d["workflow_ref"] == "docs@v1"
    assert "summarize" in d["steps"]
    assert d["context"]["include"] == ["context/**/*.md"]
