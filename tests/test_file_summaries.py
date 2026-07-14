"""Hot-file summary cache and MCP identity checks."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from server.analyze.file_summaries import MAX_SUMMARY_TOKENS, FileSummaryView
from server.mcp.tools import call_tool, open_context
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.workspaces import WorkspaceRepo


def _seed_hot_file(root: Path) -> Path:
    target = root / "src" / "service.py"
    target.parent.mkdir()
    target.write_text(
        '"""Payment service boundary."""\n\n'
        "class PaymentService:\n"
        "    def charge(self, amount: int) -> bool:\n"
        "        return amount > 0\n",
        encoding="utf-8",
    )
    database = Database(root / ".cairn" / "cairn.db")
    WorkspaceRepo.create(
        database.reader,
        Workspace(
            workspace_id="ws-hot",
            root_path=str(root),
            name="hot",
            created_at="2026-01-01T00:00:00Z",
        ),
    )
    for index in (1, 2):
        database.reader.execute(
            """INSERT INTO traces (
                 trace_id, workspace_id, source, external_id, started_at, status
               ) VALUES (?, 'ws-hot', 'codex', ?, ?, 'completed')""",
            (f"trace-{index}", f"trace-{index}", f"2026-01-0{index}T00:00:00Z"),
        )
        database.reader.execute(
            """INSERT INTO spans (
                 span_id, trace_id, seq, kind, name, status, path_rel, started_at
               ) VALUES (?, ?, 1, 'tool_call', 'read', 'ok', 'src/service.py', ?)""",
            (f"span-{index}", f"trace-{index}", f"2026-01-0{index}T00:01:00Z"),
        )
    FileSummaryView("ws-hot").compute(database.reader, "trace-2")
    database.reader.commit()
    row = database.reader.execute(
        "SELECT * FROM file_read_cache WHERE workspace_id = 'ws-hot'"
    ).fetchone()
    assert row is not None
    assert row["read_count"] == 2
    assert row["summary_tokens"] <= MAX_SUMMARY_TOKENS
    assert "PaymentService" in row["summary"]
    database.close()
    return target


def test_before_you_read_returns_summary_only_while_file_is_unchanged(tmp_path: Path) -> None:
    target = _seed_hot_file(tmp_path)
    context = open_context(tmp_path)
    try:
        unchanged = call_tool(context, "cairn_before_you_read", {"path": "src/service.py"})
        assert unchanged["should_read"] is False
        assert unchanged["unchanged"] is True
        assert unchanged["mode"] == "deterministic_summary"
        assert unchanged["summary_tokens"] <= MAX_SUMMARY_TOKENS
        assert "PaymentService" in unchanged["summary"]

        target.write_text("class ChangedService:\n    pass\n", encoding="utf-8")
        changed = call_tool(context, "cairn_before_you_read", {"path": "src/service.py"})
        assert changed["should_read"] is True
        assert changed["reason"] == "file changed since Cairn cached it"
        assert "summary" not in changed
    finally:
        context.close()


def test_before_you_read_keeps_mcp_database_read_only(tmp_path: Path) -> None:
    _seed_hot_file(tmp_path)
    context = open_context(tmp_path)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            context.conn.execute("DELETE FROM file_read_cache")
    finally:
        context.close()


def test_before_you_read_rejects_paths_outside_workspace(tmp_path: Path) -> None:
    _seed_hot_file(tmp_path)
    context = open_context(tmp_path)
    try:
        result = call_tool(context, "cairn_before_you_read", {"path": "../secret.txt"})
        assert result["should_read"] is True
        assert result["reason"] == "path is outside the active workspace"
    finally:
        context.close()
