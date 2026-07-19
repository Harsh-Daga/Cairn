"""cairn_context_budget MCP tool coverage."""

from __future__ import annotations

from pathlib import Path

from server.mcp.tools import call_tool, open_context
from server.store.db import connect
from server.store.migrate import migrate


def _seed(db_path: Path, *, dual_active: bool = False) -> None:
    conn = connect(db_path)
    migrate(conn)
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) "
        "VALUES ('ws1', '/tmp', 'demo', '2026-06-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, ended_at, status, "
        "title, input_tokens, output_tokens, cost, span_count, context_window, peak_context_pct) "
        "VALUES ('tr1', 'ws1', 'claude_code', '2026-06-01T10:00:00Z', NULL, 'running', "
        "'fix tests', 1000, 200, 0.5, 2, 200000, 42.5)"
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, input_tokens, output_tokens) "
        "VALUES ('sp1', 'tr1', NULL, 1, 'llm_call', 'model', 'ok', NULL, 800, 100)"
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, input_tokens, output_tokens) "
        "VALUES ('sp2', 'tr1', NULL, 2, 'tool_call', 'read', 'ok', 'src/app.py', 200, 0)"
    )
    conn.execute(
        """
        INSERT INTO context_regions (
          span_id, region, tokens, cost, content_hash,
          first_turn, last_seen_turn, still_in_window
        ) VALUES
          ('sp1', 'system', 120, 0.01, 'sys1', 1, 1, 1),
          ('sp1', 'user', 80, 0.0, 'usr1', 1, 1, 1),
          ('sp1', 'history', 400, 0.05, 'hist1', 1, 2, 0),
          ('sp2', 'tool_result', 900, 0.1, 'tool1', 2, 2, 0),
          ('sp2', 'tool_schema', 150, 0.02, 'schema1', 2, 2, 1)
        """
    )
    if dual_active:
        conn.execute(
            "INSERT INTO traces (trace_id, workspace_id, source, started_at, ended_at, status, "
            "title, input_tokens, output_tokens, cost, span_count) "
            "VALUES ('tr2', 'ws1', 'claude_code', '2026-06-01T11:00:00Z', NULL, 'running', "
            "'other', 10, 5, 0.01, 0)"
        )
    conn.commit()
    conn.close()


def test_context_budget_composition_and_conservative_suggestion(tmp_path: Path) -> None:
    db_dir = tmp_path / ".cairn"
    db_dir.mkdir()
    _seed(db_dir / "cairn.db")
    ctx = open_context(tmp_path)
    try:
        result = call_tool(ctx, "cairn_context_budget", {})
    finally:
        ctx.close()

    assert result.get("trace_id") == "tr1"
    assert "error" not in result
    assert result["read_only"] is True
    assert result["provider_call"] is False
    assert result["estimate_status"] == "measured"
    assert result["data_as_of"] == "2026-06-01T10:00:00Z"
    assert result["consultation"] == "recorded"
    regions = {row["region"]: row["tokens"] for row in result["composition"]}
    assert regions["tool_result"] == 900
    assert regions["history"] == 400
    assert regions["user"] == 80
    assert result["largest_removable"][0]["region"] == "tool_result"
    assert result["largest_removable"][0]["stale"] is True
    assert "user" not in {row["region"] for row in result["largest_removable"]}
    assert result["suggestion"]["conservative"] is True
    assert result["suggestion"]["region"] == "tool_result"
    assert any("Read-only" in note for note in result["limitations"])


def test_context_budget_requires_trace_when_ambiguous(tmp_path: Path) -> None:
    db_dir = tmp_path / ".cairn"
    db_dir.mkdir()
    _seed(db_dir / "cairn.db", dual_active=True)
    ctx = open_context(tmp_path)
    try:
        ambiguous = call_tool(ctx, "cairn_context_budget", {})
        explicit = call_tool(ctx, "cairn_context_budget", {"trace_id": "tr1"})
    finally:
        ctx.close()

    assert ambiguous["error"] == "ambiguous_session"
    assert {c["trace_id"] for c in ambiguous["candidates"]} == {"tr1", "tr2"}
    assert explicit["trace_id"] == "tr1"
    assert explicit["suggestion"]["region"] == "tool_result"


def test_context_budget_missing_trace_and_partial_session(tmp_path: Path) -> None:
    db_dir = tmp_path / ".cairn"
    db_dir.mkdir()
    conn = connect(db_dir / "cairn.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) "
        "VALUES ('ws1', '/tmp', 'demo', '2026-06-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "input_tokens, output_tokens, cost, span_count) "
        "VALUES ('tr-empty', 'ws1', 'claude_code', '2026-06-01T10:00:00Z', 'completed', "
        "'empty', 50, 10, 0.0, 0)"
    )
    conn.commit()
    conn.close()

    ctx = open_context(tmp_path)
    try:
        missing = call_tool(ctx, "cairn_context_budget", {"trace_id": "nope"})
        partial = call_tool(ctx, "cairn_context_budget", {"trace_id": "tr-empty"})
    finally:
        ctx.close()

    assert missing["error"] == "trace_not_found"
    assert partial["composition"] == []
    assert partial["estimate_status"] == "estimated"
    assert partial["suggestion"] is None
    assert any("No context_regions" in note for note in partial["limitations"])
