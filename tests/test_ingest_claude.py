"""Ported ingest tests — Claude Code."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.ingest import tokenize
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.writer import IngestWriter
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


@pytest.fixture
def ingest_writer(tmp_path: Path) -> IngestWriter:
    root = tmp_path / "proj"
    root.mkdir()
    db = Database(tmp_path / "cairn.db")
    ws_id = new_ulid()
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(root),
            name="proj",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    db.reader.commit()
    return IngestWriter(db, ws_id, root)


def test_ingest_claude_session(ingest_writer: IngestWriter, tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter(tmp_path / "proj", ingest_writer.workspace_id)
    parsed = adapter.parse_path(FIXTURES / "wasteful_session.jsonl")
    assert parsed is not None
    result = ingest_writer.ingest(parsed)
    assert result.inserted
    assert result.span_count > 0
    trace = TraceRepo.get(ingest_writer._db.reader, result.trace_id)
    assert trace is not None
    assert trace.input_tokens > 0
    assert trace.cost_source in {"observed", "priced", "absent"}


def test_claude_input_tokens_distrust_and_estimation(tmp_path: Path) -> None:
    tokenize.reset_calibration()
    adapter = ClaudeCodeAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "claude_estimation.jsonl")
    assert parsed is not None

    assistant_msgs = [e for e in parsed.events if e["type"] == "assistant_message"]
    assert len(assistant_msgs) == 2

    first = assistant_msgs[0]
    assert first["input_estimated"] == 1
    est_fresh, _ = tokenize.count_tokens(
        "Fix the auth bug in the login module and explain your reasoning step by step.",
        model="claude-sonnet-4-5",
    )
    assert first["input_tokens"] >= 150
    assert first["input_tokens"] == 150 + est_fresh
    assert first["output_estimated"] == 1
    assert first["output_tokens"] >= 15

    assert parsed.usage.input_tokens < 9999
    assert parsed.usage.output_tokens < 9999


def test_claude_sidechain_fixture_parses(tmp_path: Path) -> None:
    adapter = ClaudeCodeAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "claude_sidechain_mini.jsonl")
    assert parsed is not None
    assert len(parsed.events) >= 2


def test_ingest_deterministic_ids(ingest_writer: IngestWriter, tmp_path: Path) -> None:
    tokenize.reset_calibration()
    adapter = ClaudeCodeAdapter(tmp_path / "proj", ingest_writer.workspace_id)
    path = FIXTURES / "wasteful_session.jsonl"
    first = adapter.parse_path(path)
    assert first is not None
    r1 = ingest_writer.ingest(first)
    trace1 = TraceRepo.get(ingest_writer._db.reader, r1.trace_id)
    spans1 = SpanRepo.list_by_trace(ingest_writer._db.reader, r1.trace_id)

    db2_path = tmp_path / "cairn2.db"
    db2 = Database(db2_path)
    ws_id = ingest_writer.workspace_id
    WorkspaceRepo.create(
        db2.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(tmp_path / "proj"),
            name="proj",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    db2.reader.commit()
    writer2 = IngestWriter(db2, ws_id, tmp_path / "proj")
    r2 = writer2.ingest(first)
    trace2 = TraceRepo.get(db2.reader, r2.trace_id)
    spans2 = SpanRepo.list_by_trace(db2.reader, r2.trace_id)

    assert trace1 is not None and trace2 is not None
    assert trace1.trace_id == trace2.trace_id
    assert trace1.input_tokens == trace2.input_tokens
    assert trace1.output_tokens == trace2.output_tokens
    assert [s.span_id for s in spans1] == [s.span_id for s in spans2]
    db2.close()
