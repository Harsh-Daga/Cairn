"""Trace diff endpoint tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from server.analyze.diff import MAX_LCS_CELLS, align_turns_lcs
from server.models.outcome import Diagnostic, Outcome
from server.models.span import Span
from server.models.trace import Trace
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.diagnostics import DiagnosticRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.store.repos.workspaces import WorkspaceRepo


def _insert_compare_trace(root: Path, workspace_id: str) -> str:
    db = Database(root / ".cairn" / "cairn.db")
    trace_id = "TRACE_DIFF_B"
    trace = Trace(
        trace_id=trace_id,
        workspace_id=workspace_id,
        source="claude_code",
        external_id="trace-diff-b",
        title="compare trace",
        project="compare-project",
        model="model-b",
        started_at="2026-07-18T00:00:00Z",
        ended_at="2026-07-18T00:00:03Z",
        status="completed",
        input_tokens=180,
        output_tokens=80,
        cost=0.9,
        cost_source="observed",
        span_count=3,
        waste_tokens=20,
    )
    TraceRepo.create(db.reader, trace)
    spans = [
        Span(
            span_id="DIFF_B_1",
            trace_id=trace_id,
            seq=1,
            kind="llm_call",
            name="plan",
            input_tokens=100,
            output_tokens=50,
            status="ok",
            model="model-b",
        ),
        Span(
            span_id="DIFF_B_2",
            trace_id=trace_id,
            seq=2,
            kind="tool_call",
            name="read_file",
            input_tokens=40,
            output_tokens=10,
            waste_tokens=20,
            status="error",
            model="model-b",
        ),
        Span(
            span_id="DIFF_B_3",
            trace_id=trace_id,
            seq=3,
            kind="tool_call",
            name="write_file",
            input_tokens=40,
            output_tokens=20,
            status="ok",
            model="model-b",
        ),
    ]
    for span in spans:
        SpanRepo.create(db.reader, span)
    OutcomeRepo.upsert(
        db.reader,
        Outcome(
            trace_id=trace_id,
            tests_run=3,
            tests_failed=1,
            build_status="failed",
            outcome_label="fail",
        ),
    )
    DiagnosticRepo.upsert(
        db.reader,
        Diagnostic(
            trace_id=trace_id,
            failure_origin_span_id="DIFF_B_2",
            primary_category="tool_failure",
            failure_signature="recorded-test-signature",
        ),
    )
    db.reader.commit()
    db.close()
    return trace_id


def test_trace_diff_endpoint(api_client: TestClient, api_workspace: tuple[Path, str, str]) -> None:
    root, workspace_id, trace_a = api_workspace
    trace_b = _insert_compare_trace(root, workspace_id)

    resp = api_client.get(f"/api/traces/diff?a={trace_a}&b={trace_b}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["a"]["trace_id"] == trace_a
    assert body["b"]["trace_id"] == trace_b
    assert "summary" in body
    assert "turns" in body
    assert "analysis" in body
    assert len(body["turns"]) >= 1
    assert any(turn["op"] == "insert" for turn in body["turns"])
    analysis = body["analysis"]
    assert analysis["tokens_b"] == 260
    assert analysis["duration_ms_b"] == 3_000
    assert analysis["models_b"] == ["model-b"]
    assert analysis["outcome_b"]["outcome_label"] == "fail"
    assert analysis["diagnostic_b"]["failure_origin_span_id"] == "DIFF_B_2"
    assert analysis["comparability"]["state"] in {"limited", "not_comparable"}
    assert "caused" in analysis["comparability"]["limitation"]
    assert any(item["span_id"] == "DIFF_B_2" for item in analysis["evidence"])
    assert any(item["basis"] == "limitation" for item in analysis["what_changed"])


def test_trace_diff_not_found(api_client: TestClient, api_workspace: tuple[Path, str, str]) -> None:
    _root, _workspace_id, trace_a = api_workspace
    resp = api_client.get(f"/api/traces/diff?a={trace_a}&b=missing-trace")
    assert resp.status_code == 404


def test_trace_diff_cannot_resolve_trace_from_another_workspace(
    api_client: TestClient,
    api_workspace: tuple[Path, str, str],
) -> None:
    root, _workspace_id, trace_a = api_workspace
    db = Database(root / ".cairn" / "cairn.db")
    foreign_workspace_id = "FOREIGN_WORKSPACE"
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=foreign_workspace_id,
            root_path=str(root / "foreign"),
            name="foreign",
            created_at="2026-07-18T00:00:00Z",
        ),
    )
    TraceRepo.create(
        db.reader,
        Trace(
            trace_id="FOREIGN_TRACE",
            workspace_id=foreign_workspace_id,
            source="codex",
        ),
    )
    db.reader.commit()
    db.close()

    response = api_client.get(f"/api/traces/diff?a={trace_a}&b=FOREIGN_TRACE")
    assert response.status_code == 404


def test_large_alignment_uses_bounded_position_path() -> None:
    count = int(MAX_LCS_CELLS**0.5) + 1
    spans_a = [
        Span(span_id=f"A_{index}", trace_id="A", seq=index, kind="tool_call", name="read")
        for index in range(count)
    ]
    spans_b = [
        Span(span_id=f"B_{index}", trace_id="B", seq=index, kind="tool_call", name="read")
        for index in range(count)
    ]
    aligned = align_turns_lcs(spans_a, spans_b)
    assert len(aligned) == count
    assert all(item.op == "match" for item in aligned)
