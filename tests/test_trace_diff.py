"""Trace diff endpoint tests."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from server.models.span import Span
from server.models.trace import Trace
from server.store.db import Database
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo


def _insert_compare_trace(root: Path, workspace_id: str) -> str:
    db = Database(root / ".cairn" / "cairn.db")
    trace_id = "TRACE_DIFF_B"
    trace = Trace(
        trace_id=trace_id,
        workspace_id=workspace_id,
        source="claude_code",
        external_id="trace-diff-b",
        title="compare trace",
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
        ),
    ]
    for span in spans:
        SpanRepo.create(db.reader, span)
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
    assert len(body["turns"]) >= 1
    assert any(turn["op"] == "insert" for turn in body["turns"])


def test_trace_diff_not_found(api_client: TestClient, api_workspace: tuple[Path, str, str]) -> None:
    _root, _workspace_id, trace_a = api_workspace
    resp = api_client.get(f"/api/traces/diff?a={trace_a}&b=missing-trace")
    assert resp.status_code == 404
