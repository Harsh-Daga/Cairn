"""Pillar 5 tests — MCP stdio handshake + tools + Jaccard dedup + aged facts."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator
from cairn.ingest.writer import CaptureWriter
from cairn.mcp.server import serve


def _ingest(
    tmp_path: Path,
    events,
    tool_calls,
    *,
    model="claude-sonnet-4-5",
    external_id="s1",
    started_at=None,
):
    w = CaptureWriter(tmp_path)
    res = w._ingest_session(
        source="claude-code",
        external_id=external_id,
        cwd=str(tmp_path),
        git_branch=None,
        started_at=started_at or datetime.now(UTC).isoformat(),
        ended_at=None,
        model=model,
        events=events,
        tool_calls=tool_calls,
        usage=UsageAccumulator().usage,
    )
    w.close()
    return res.run_id


def _read_events_with_a_py():
    return [
        {"type": "user_prompt", "text": "read a.py", "text_hash": "h1"},
        {
            "type": "tool_call",
            "tool_use_id": "t1",
            "name": "read",
            "args_inline": {"file_path": "a.py"},
            "args_hash": "ah1",
        },
        {
            "type": "tool_result",
            "tool_use_id": "t1",
            "result_inline": "content of a.py here",
            "result_hash": "rh1",
        },
        {
            "type": "assistant_message",
            "text": "done reading a.py content",
            "model": "claude-sonnet-4-5",
            "input_tokens": 100,
            "output_tokens": 50,
            "usage": {"input_tokens": 100, "output_tokens": 50},
        },
        {"type": "user_prompt", "text": "again", "text_hash": "h2"},
        {
            "type": "tool_call",
            "tool_use_id": "t2",
            "name": "read",
            "args_inline": {"file_path": "a.py"},
            "args_hash": "ah2",
        },
        {
            "type": "tool_result",
            "tool_use_id": "t2",
            "result_inline": "content of a.py here plus a bit",
            "result_hash": "rh2",
        },
        {
            "type": "assistant_message",
            "text": "ok",
            "model": "claude-sonnet-4-5",
            "input_tokens": 120,
            "output_tokens": 40,
            "usage": {"input_tokens": 120, "output_tokens": 40},
        },
    ]


def _send(tmp_path: Path, *messages) -> list[dict]:
    stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
    stdout = io.StringIO()
    serve(tmp_path, stdin=stdin, stdout=stdout)
    return [json.loads(line) for line in stdout.getvalue().strip().splitlines() if line]


def test_mcp_auto_install_defaults_on(tmp_path: Path, monkeypatch) -> None:
    from cairn.config import mcp_auto_install_enabled

    monkeypatch.delenv("HOME", raising=False)
    assert mcp_auto_install_enabled() is True


def test_handshake_initialize_and_tools_list(tmp_path: Path) -> None:
    _ingest(
        tmp_path,
        _read_events_with_a_py(),
        [
            ToolCallDraft("t1", "read", "ah1", 2, "a.py"),
            ToolCallDraft("t2", "read", "ah2", 6, "a.py"),
        ],
    )
    responses = _send(
        tmp_path,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    )
    by_id = {r["id"]: r for r in responses if "id" in r}
    assert by_id[1]["result"]["protocolVersion"]
    assert by_id[1]["result"]["serverInfo"]["name"] == "cairn"
    names = {t["name"] for t in by_id[2]["result"]["tools"]}
    assert "cairn_have_i_read" in names
    assert "cairn_project_primer" in names
    assert "cairn_replay_last" in names
    # The notification got no response.
    assert all("id" in r for r in responses)


def test_have_i_read_with_jaccard_dedup(tmp_path: Path) -> None:
    _ingest(
        tmp_path,
        _read_events_with_a_py(),
        [
            ToolCallDraft("t1", "read", "ah1", 2, "a.py"),
            ToolCallDraft("t2", "read", "ah2", 6, "a.py"),
        ],
    )
    responses = _send(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cairn_have_i_read", "arguments": {"path": "a.py"}},
        },
    )
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    assert result["read"] is True
    # Two trivially-different reads dedup to one distinct read.
    assert result["times"] == 1
    assert result["note"] is not None


def test_have_i_read_negative(tmp_path: Path) -> None:
    _ingest(tmp_path, _read_events_with_a_py(), [ToolCallDraft("t1", "read", "ah1", 2, "a.py")])
    responses = _send(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cairn_have_i_read", "arguments": {"path": "other.py"}},
        },
    )
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    assert result["read"] is False


def test_project_primer_returns_system_primer(tmp_path: Path) -> None:
    _ingest(tmp_path, _read_events_with_a_py(), [ToolCallDraft("t1", "read", "ah1", 2, "a.py")])
    responses = _send(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cairn_project_primer", "arguments": {"project": tmp_path.name}},
        },
    )
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    assert "primer" in result
    assert tmp_path.name in result["primer"]
    assert "waste_patterns" in result
    assert "facts" in result


def test_replay_last_returns_findings(tmp_path: Path) -> None:
    _ingest(tmp_path, _read_events_with_a_py(), [ToolCallDraft("t1", "read", "ah1", 2, "a.py")])
    responses = _send(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cairn_replay_last", "arguments": {}},
        },
    )
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    assert result["run_id"] is not None
    assert isinstance(result["waste"], list)


def test_aged_facts_carry_verify_flag(tmp_path: Path) -> None:
    # Insert an applied optimization with an old applied_at → age > 30 days.
    _ingest(tmp_path, _read_events_with_a_py(), [ToolCallDraft("t1", "read", "ah1", 2, "a.py")])
    w = CaptureWriter(tmp_path)
    w.connection.execute(
        """INSERT INTO optimizations (opt_id, created_at, target_file, block_key,
           kind, content, evidence_json, status, applied_at)
           VALUES ('o1', '2026-01-01T00:00:00', 'a/AGENTS.md', 'tips',
           'guide', 'do x', '{}', 'applied', '2020-01-01T00:00:00')"""
    )
    w.connection.commit()
    w.close()
    responses = _send(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cairn_project_primer", "arguments": {"project": tmp_path.name}},
        },
    )
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    aged = [f for f in result["facts"] if f.get("verify_before_relying")]
    assert aged, "expected at least one aged fact with verify_before_relying"


def test_spend_today_empty(tmp_path: Path) -> None:
    # No runs today → empty sources.
    _ingest(
        tmp_path,
        _read_events_with_a_py(),
        [ToolCallDraft("t1", "read", "ah1", 2, "a.py")],
        started_at="2020-01-01T00:00:00",
    )  # not today
    responses = _send(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "cairn_spend_today", "arguments": {}},
        },
    )
    result = json.loads(responses[0]["result"]["content"][0]["text"])
    assert result["sources"] == []


def test_parse_error_returns_jsonrpc_error(tmp_path: Path) -> None:
    stdin = io.StringIO("not json\n")
    stdout = io.StringIO()
    serve(tmp_path, stdin=stdin, stdout=stdout)
    resp = json.loads(stdout.getvalue().strip())
    assert resp["error"]["code"] == -32700
