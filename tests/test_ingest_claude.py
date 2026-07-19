"""Ported ingest tests — Claude Code."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from server.ingest import tokenize
from server.ingest.adapters.claude_code import parse_jsonl_file
from server.ingest.adapters.claude_code_adapter import ClaudeCodeAdapter
from server.ingest.parse_health import inspect_unknown_fields
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


def test_ingest_refreshes_an_existing_active_session(
    ingest_writer: IngestWriter, tmp_path: Path
) -> None:
    adapter = ClaudeCodeAdapter(tmp_path / "proj", ingest_writer.workspace_id)
    parsed = adapter.parse_path(FIXTURES / "claude_code_mini.jsonl")
    assert parsed is not None

    first = ingest_writer.ingest(parsed)
    first_trace = TraceRepo.get(ingest_writer._db.reader, first.trace_id)
    assert first_trace is not None

    refreshed = replace(
        parsed,
        ended_at="2026-01-01T00:10:00Z",
        events=[
            *parsed.events,
            {
                "type": "assistant_message",
                "text_inline": "A later live-session response",
                "model": parsed.model,
            },
        ],
    )
    second = ingest_writer.ingest(refreshed)
    second_trace = TraceRepo.get(ingest_writer._db.reader, first.trace_id)

    assert second.inserted is False
    assert second.trace_id == first.trace_id
    assert second.span_count == first.span_count + 1
    assert second_trace is not None
    assert second_trace.ended_at == "2026-01-01T00:10:00Z"
    assert second_trace.span_count == first_trace.span_count + 1
    stored_spans = SpanRepo.list_by_trace(ingest_writer._db.reader, first.trace_id)
    assert len(stored_spans) == second.span_count


def test_claude_keeps_additive_tools_across_shared_request_id(tmp_path: Path) -> None:
    """One requestId can stream multiple tool batches; all tools must be kept."""
    path = tmp_path / "dup-request.jsonl"
    records = [
        {
            "type": "user",
            "sessionId": "sess-dup",
            "uuid": "u1",
            "parentUuid": None,
            "timestamp": "2026-06-01T10:00:00Z",
            "cwd": str(tmp_path),
            "gitBranch": "main",
            "message": {"role": "user", "content": [{"type": "text", "text": "edit it"}]},
        },
        {
            "type": "assistant",
            "sessionId": "sess-dup",
            "uuid": "a1",
            "parentUuid": "u1",
            "timestamp": "2026-06-01T10:00:01Z",
            "requestId": "req_shared",
            "message": {
                "role": "assistant",
                "model": "claude-test",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_bash",
                        "name": "Bash",
                        "input": {"command": "ls"},
                    }
                ],
                "usage": {
                    "input_tokens": 2,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 10,
                },
            },
        },
        {
            "type": "assistant",
            "sessionId": "sess-dup",
            "uuid": "a2",
            "parentUuid": "u1",
            "timestamp": "2026-06-01T10:00:02Z",
            "requestId": "req_shared",
            "message": {
                "role": "assistant",
                "model": "claude-test",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tool_read",
                        "name": "Read",
                        "input": {"file_path": str(tmp_path / "a.py")},
                    }
                ],
                "usage": {
                    "input_tokens": 2,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 10,
                },
            },
        },
        {
            # Inflated usage-only duplicate must not replace cache-backed usage.
            "type": "assistant",
            "sessionId": "sess-dup",
            "uuid": "a3",
            "parentUuid": "u1",
            "timestamp": "2026-06-01T10:00:03Z",
            "requestId": "req_shared",
            "message": {
                "role": "assistant",
                "model": "claude-test",
                "content": [],
                "usage": {"input_tokens": 9999, "output_tokens": 9999},
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")

    parsed = parse_jsonl_file(path, repo_root=tmp_path)
    assert parsed is not None
    assert [t.name for t in parsed.tool_calls] == ["Bash", "Read"]
    assert parsed.usage.usage.input_tokens < 9999
    assert parsed.usage.usage.output_tokens < 9999
    assert parsed.usage.usage.cache_read_tokens == 100


def test_claude_ignores_synthetic_model_overwrite(tmp_path: Path) -> None:
    path = tmp_path / "synthetic-model.jsonl"
    records = [
        {
            "type": "user",
            "sessionId": "sess-model",
            "uuid": "u1",
            "timestamp": "2026-06-01T10:00:00Z",
            "cwd": str(tmp_path),
            "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
        },
        {
            "type": "assistant",
            "sessionId": "sess-model",
            "uuid": "a1",
            "timestamp": "2026-06-01T10:00:01Z",
            "requestId": "req_1",
            "message": {
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [{"type": "text", "text": "hello"}],
                "usage": {"input_tokens": 10, "output_tokens": 4},
            },
        },
        {
            "type": "assistant",
            "sessionId": "sess-model",
            "uuid": "a2",
            "timestamp": "2026-06-01T10:00:02Z",
            "requestId": "req_2",
            "message": {
                "role": "assistant",
                "model": "<synthetic>",
                "content": [{"type": "text", "text": "bye"}],
                "usage": {"input_tokens": 2, "output_tokens": 2},
            },
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    parsed = parse_jsonl_file(path, repo_root=tmp_path)
    assert parsed is not None
    assert parsed.model == "claude-sonnet-4-5"


def test_claude_agent_id_camel_case_is_expected(tmp_path: Path) -> None:
    path = tmp_path / "agent-id.jsonl"
    records = [
        {
            "type": "assistant",
            "sessionId": "sess-agent",
            "uuid": "a1",
            "timestamp": "2026-06-01T10:00:00Z",
            "cwd": str(tmp_path),
            "agentId": "agent-sidechain-1",
            "attributionAgent": "Explore",
            "message": {
                "role": "assistant",
                "model": "claude-test",
                "content": [{"type": "text", "text": "ok"}],
                "usage": {"input_tokens": 3, "output_tokens": 1},
            },
        }
    ]
    path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    assert inspect_unknown_fields("claude_code", path) == {}
    parsed = parse_jsonl_file(path, repo_root=tmp_path)
    assert parsed is not None
    assert parsed.events[0].get("agent_id") == "agent-sidechain-1"


def test_claude_live_metadata_keys_are_expected(tmp_path: Path) -> None:
    path = tmp_path / "meta.jsonl"
    records = [
        {
            "type": "mode",
            "sessionId": "sess-meta",
            "uuid": "m1",
            "timestamp": "2026-06-01T10:00:00Z",
            "userType": "external",
            "version": "1.2.3",
            "mode": "default",
            "permissionMode": "default",
        },
        {
            "type": "user",
            "sessionId": "sess-meta",
            "uuid": "u1",
            "timestamp": "2026-06-01T10:00:01Z",
            "cwd": str(tmp_path),
            "message": {"role": "user", "content": [{"type": "text", "text": "hi"}]},
            "promptId": "p1",
            "entrypoint": "cli",
        },
    ]
    path.write_text("\n".join(json.dumps(row) for row in records) + "\n", encoding="utf-8")
    assert inspect_unknown_fields("claude_code", path) == {}
