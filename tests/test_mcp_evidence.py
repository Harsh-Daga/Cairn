"""MCP evidence tools: verification, policy, regression, next-evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from server.mcp.tools import ToolsContext, call_tool, list_tools
from server.regression.create import create_regression_from_trace
from server.store.db import connect
from server.store.migrate import migrate
from server.util.ids import new_ulid
from server.util.private_files import write_private_text


def _seed(root: Path) -> tuple[str, str]:
    cairn = root / ".cairn"
    cairn.mkdir(parents=True)
    conn = connect(cairn / "cairn.db")
    migrate(conn)
    ws_id = new_ulid()
    trace_id = "tr-mcp-ev"
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws_id, str(root), "mcp-ev", datetime.now(UTC).isoformat()),
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
        "VALUES (?, ?, 'cursor', '2026-07-01T10:00:00Z', 'completed', 'fix', "
        "80, 20, 1.0, 'priced', 2, 0)",
        (trace_id, ws_id),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, text_inline) VALUES "
        "('sp1', ?, NULL, 1, 'user_msg', 'user', 'ok', NULL, 'Fix auth tests'),"
        "('sp2', ?, 'sp1', 2, 'tool_call', 'pytest', 'ok', 'src/auth/a.py', NULL)",
        (trace_id, trace_id),
    )
    conn.execute(
        "INSERT INTO outcomes (trace_id, outcome_label, files_changed_json, captured_at) "
        "VALUES (?, 'success', ?, ?)",
        (trace_id, json.dumps(["src/auth/a.py"]), datetime.now(UTC).isoformat()),
    )
    conn.commit()
    write_private_text(
        cairn / "config.toml",
        """
[policy]
[[policy.path_risks]]
pattern = "**/auth/**"
risk = "high"

[[policy.commands]]
pattern = "rm\\\\s+-rf"
mode = "forbidden"
""",
    )
    conn.close()
    return ws_id, trace_id


def test_evidence_tools_are_registered() -> None:
    names = {tool["name"] for tool in list_tools()}
    assert {
        "cairn_verification_status",
        "cairn_policy_check",
        "cairn_regression_context",
        "cairn_next_evidence",
        "cairn_handoff",
    } <= names
    assert len(names) == 13


def test_verification_policy_next_evidence(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _ws_id, trace_id = _seed(root)
    conn = connect(root / ".cairn" / "cairn.db")
    ctx = ToolsContext(conn=conn, workspace_root=root, workspace_id=_ws_id)

    status = call_tool(ctx, "cairn_verification_status", {"trace_id": trace_id})
    assert status["schema"] == "cairn.mcp.verification_status.v1"
    assert status["status"] in {"debt", "verified", "unverified", "failed", "unknown"}
    assert status["consultation"] == "recorded"

    policy = call_tool(
        ctx, "cairn_policy_check", {"path": "src/auth/a.py", "command": "rm -rf /tmp"}
    )
    assert policy["schema"] == "cairn.mcp.policy_check.v1"
    assert policy["executed"] is False
    assert policy["review_risk"] == "high"
    assert any(f["enforcement_source"] == "observed_violation" for f in policy["findings"])

    nxt = call_tool(ctx, "cairn_next_evidence", {"trace_id": trace_id})
    assert nxt["schema"] == "cairn.mcp.next_evidence.v1"
    assert nxt["next_check"]["executed"] is False
    assert nxt["next_check"]["approval_class"] in {
        "read_only",
        "local_test",
        "mutating",
        "destructive",
    }
    ctx.close()


def test_regression_context_requires_id_when_ambiguous(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    ws_id, trace_id = _seed(root)
    conn = connect(root / ".cairn" / "cairn.db")
    created = create_regression_from_trace(
        conn, workspace_root=root, workspace_id=ws_id, trace_id=trace_id
    )
    assert created["ok"]
    ctx = ToolsContext(conn=conn, workspace_root=root, workspace_id=ws_id)
    single = call_tool(ctx, "cairn_regression_context", {})
    assert single["schema"] == "cairn.mcp.regression_context.v1"
    assert single["executed"] is False
    assert single["regression_id"] == created["regression_id"]
    ctx.close()
