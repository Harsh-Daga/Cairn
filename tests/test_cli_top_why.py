"""CLI top/why coverage for stable JSON and exit codes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from server.cli import app
from server.store.db import connect
from server.store.migrate import migrate
from server.util.ids import new_ulid


def _seed_workspace(root: Path, *, with_error: bool = True) -> str:
    cairn = root / ".cairn"
    cairn.mkdir(parents=True)
    db_path = cairn / "cairn.db"
    conn = connect(db_path)
    migrate(conn)
    ws_id = new_ulid()
    trace_id = "tr-why-1"
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws_id, str(root), "cli-top-why", datetime.now(UTC).isoformat()),
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "input_tokens, output_tokens, cost, cost_source, span_count) "
        "VALUES (?, ?, 'cursor', '2026-07-01T10:00:00Z', 'completed', 'broken run', "
        "100, 20, 1.5, 'priced', 2)",
        (trace_id, ws_id),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status) "
        "VALUES ('sp1', ?, NULL, 1, 'tool_call', 'pytest', ?)",
        (trace_id, "error" if with_error else "ok"),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status) "
        "VALUES ('sp2', ?, NULL, 2, 'llm_call', 'model', 'ok')",
        (trace_id,),
    )
    conn.commit()
    conn.close()
    return trace_id


def test_cairn_top_once_json(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _seed_workspace(root)
    monkeypatch.chdir(root)
    runner = CliRunner()
    result = runner.invoke(app, ["top", "--once", "--json", "--workspace", str(root)])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "cairn.top.v1"
    assert payload["rows"]
    assert payload["rows"][0]["trace_id"] == "tr-why-1"
    assert payload["rows"][0]["cost"] == 1.5


def test_cairn_why_markdown_and_missing(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    trace_id = _seed_workspace(root, with_error=True)
    monkeypatch.chdir(root)
    runner = CliRunner()

    ok = runner.invoke(app, ["why", trace_id, "--workspace", str(root)])
    assert ok.exit_code == 0, ok.output
    assert "postmortem" in ok.output.lower() or "Uncertainty" in ok.output

    as_json = runner.invoke(app, ["why", trace_id, "--json", "--workspace", str(root)])
    assert as_json.exit_code == 0, as_json.output
    body = json.loads(as_json.output)
    assert body["schema"] == "cairn.why.v1"
    assert body["available"] is True
    assert body["postmortem"]["markdown"]

    missing = runner.invoke(app, ["why", "missing", "--workspace", str(root)])
    assert missing.exit_code == 1


def test_cairn_why_no_evidence_exits_two(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    trace_id = _seed_workspace(root, with_error=False)
    monkeypatch.chdir(root)
    runner = CliRunner()
    result = runner.invoke(app, ["why", trace_id, "--workspace", str(root)])
    assert result.exit_code == 2
    assert "No postmortem available" in (result.output + result.stderr)

    as_json = runner.invoke(app, ["why", trace_id, "--json", "--workspace", str(root)])
    assert as_json.exit_code == 2
    body = json.loads(as_json.stdout or as_json.output)
    assert body["available"] is False
    assert body["postmortem"] is None
