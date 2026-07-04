"""Phase 3 — cairn_should_i_stop MCP tool tests."""

from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path

from cairn.diagnose.should_stop import should_stop_verdict
from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator
from cairn.ingest.writer import CaptureWriter
from cairn.mcp.server import serve
from cairn.mcp.tools import open_context


def _ingest_events(tmp_path: Path, events, tool_calls, *, external_id="loop") -> str:
    w = CaptureWriter(tmp_path)
    res = w._ingest_session(
        source="claude-code",
        external_id=external_id,
        cwd=str(tmp_path),
        git_branch=None,
        started_at=datetime.now(UTC).isoformat(),
        ended_at=None,
        model="claude-sonnet-4-5",
        events=events,
        tool_calls=tool_calls,
        usage=UsageAccumulator().usage,
    )
    w.close()
    return res.run_id


def _loop_events(n: int = 4) -> list[dict]:
    events: list[dict] = [{"type": "user_prompt", "text": "grep again", "text_hash": "h0"}]
    for i in range(n):
        uid = f"t{i}"
        events.extend(
            [
                {
                    "type": "tool_call",
                    "tool_use_id": uid,
                    "name": "grep",
                    "args_inline": {"pattern": "foo"},
                    "args_hash": "same",
                },
                {
                    "type": "tool_result",
                    "tool_use_id": uid,
                    "result_inline": "same output",
                    "result_hash": "r",
                },
            ]
        )
    events.append(
        {
            "type": "assistant_message",
            "text": "still trying",
            "input_tokens": 50,
            "output_tokens": 10,
        }
    )
    return events


def _loop_tool_calls(n: int = 4) -> list[ToolCallDraft]:
    return [ToolCallDraft(f"t{i}", "grep", "same", 2 + i * 2, None) for i in range(n)]


def test_should_i_stop_identical_tool_loop(tmp_path: Path) -> None:
    _ingest_events(tmp_path, _loop_events(4), _loop_tool_calls(4))
    ctx = open_context(tmp_path)
    try:
        from cairn.mcp.tools import call_tool

        out = call_tool(ctx, "cairn_should_i_stop", {})
    finally:
        ctx.close()
    assert out["should_stop"] is True
    assert out.get("suggestion")


def test_should_i_stop_healthy_session(tmp_path: Path) -> None:
    events = [
        {"type": "user_prompt", "text": "read a.py", "text_hash": "h1"},
        {
            "type": "tool_call",
            "tool_use_id": "t1",
            "name": "read",
            "args_inline": {"file_path": "a.py"},
            "args_hash": "a1",
        },
        {"type": "tool_result", "tool_use_id": "t1", "result_inline": "ok", "result_hash": "r1"},
        {"type": "assistant_message", "text": "done", "input_tokens": 40, "output_tokens": 10},
    ]
    _ingest_events(
        tmp_path, events, [ToolCallDraft("t1", "read", "a1", 2, "a.py")], external_id="ok"
    )
    ctx = open_context(tmp_path)
    try:
        from cairn.mcp.tools import call_tool

        out = call_tool(ctx, "cairn_should_i_stop", {})
    finally:
        ctx.close()
    assert out["should_stop"] is False


def test_should_i_stop_insufficient_signal() -> None:
    events = [
        {"type": "user_prompt", "text": "hi", "text_hash": "h"},
        {"type": "assistant_message", "text": "hello", "input_tokens": 5, "output_tokens": 3},
    ]
    out = should_stop_verdict(events)
    assert out["should_stop"] is False
    assert out["reason"] == "insufficient signal"


def test_mcp_stdio_should_i_stop(tmp_path: Path) -> None:
    _ingest_events(tmp_path, _loop_events(4), _loop_tool_calls(4), external_id="stdio")
    stdin = io.StringIO(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": "cairn_should_i_stop", "arguments": {}},
            }
        )
        + "\n"
    )
    stdout = io.StringIO()
    serve(tmp_path, stdin=stdin, stdout=stdout)
    resp = json.loads(stdout.getvalue().strip())
    result = json.loads(resp["result"]["content"][0]["text"])
    assert result["should_stop"] is True
