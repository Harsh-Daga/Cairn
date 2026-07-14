"""MCP stdio smoke tests."""

from __future__ import annotations

import io
import json
from pathlib import Path

from server.mcp.server import serve
from server.mcp.tools import call_tool, open_context
from server.store.db import connect
from server.store.migrate import migrate


def _seed_db(db_path: Path) -> None:
    conn = connect(db_path)
    migrate(conn)
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) "
        "VALUES ('ws1', '/tmp', 'demo', '2026-06-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "input_tokens, output_tokens, cost, span_count) "
        "VALUES ('tr1', 'ws1', 'claude_code', '2026-06-01T10:00:00Z', 'completed', "
        "'fix tests', 1000, 200, 0.5, 2)"
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, input_tokens, output_tokens, waste_category, waste_tokens) "
        "VALUES ('sp1', 'tr1', NULL, 1, 'tool_call', 'read', 'ok', 'src/app.py', 100, 0, NULL, 0)"
    )
    conn.commit()
    conn.close()


def test_mcp_stdio_initialize_and_list_tools(tmp_path: Path) -> None:
    db_dir = tmp_path / ".cairn"
    db_dir.mkdir()
    _seed_db(db_dir / "cairn.db")

    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        + "\n"
    )
    stdout = io.StringIO()
    assert serve(tmp_path, stdin=stdin, stdout=stdout) == 0

    lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
    assert lines[0]["result"]["serverInfo"]["name"] == "cairn"
    tool_names = {t["name"] for t in lines[1]["result"]["tools"]}
    assert "cairn_have_i_read" in tool_names
    assert "cairn_should_i_stop" in tool_names
    assert "cairn_before_you_read" in tool_names
    assert len(tool_names) == 7


def test_mcp_have_i_read_tool(tmp_path: Path) -> None:
    db_dir = tmp_path / ".cairn"
    db_dir.mkdir()
    _seed_db(db_dir / "cairn.db")

    stdin = io.StringIO(
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
        + "\n"
        + json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "cairn_have_i_read",
                    "arguments": {"path": "src/app.py"},
                },
            }
        )
        + "\n"
    )
    stdout = io.StringIO()
    serve(tmp_path, stdin=stdin, stdout=stdout)
    lines = [json.loads(line) for line in stdout.getvalue().strip().splitlines()]
    payload = json.loads(lines[1]["result"]["content"][0]["text"])
    assert payload["read"] is True
    assert payload["path"] == "src/app.py"
    event_text = (db_dir / "mcp-events.jsonl").read_text(encoding="utf-8")
    event = json.loads(event_text)
    assert event["tool_name"] == "cairn_have_i_read"
    assert event["trace_id"] == "tr1"
    assert event["after_seq"] == 1
    assert "src/app.py" not in event_text
    assert "arguments" not in event_text

    # The MCP process records only to the sidecar; its SQLite connection stays read-only.
    conn = connect(db_dir / "cairn.db")
    assert conn.execute("SELECT COUNT(*) FROM mcp_consultations").fetchone()[0] == 0
    conn.close()


def test_should_i_stop_uses_live_failing_command_detector(tmp_path: Path) -> None:
    db_dir = tmp_path / ".cairn"
    db_dir.mkdir()
    db_path = db_dir / "cairn.db"
    _seed_db(db_path)
    conn = connect(db_path)
    for seq in range(2, 8):
        conn.execute(
            """INSERT INTO spans (
                 span_id, trace_id, seq, kind, name, status, args_hash
               ) VALUES (?, 'tr1', ?, 'tool_call', 'npm test', 'error', 'same')""",
            (f"failure-{seq}", seq),
        )
    conn.commit()
    conn.close()

    context = open_context(tmp_path)
    try:
        result = call_tool(context, "cairn_should_i_stop", {})
    finally:
        context.close()
    assert result["should_stop"] is True
    assert result["pattern"] == "failing_command"
    assert result["count"] == 6
    assert result["first_seen_seq"] == 2
    assert "npm test 6×" in result["advice"]
    assert "read the error output" in result["advice"]
