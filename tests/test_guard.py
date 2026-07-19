"""Guard scan, association language, API, and CLI coverage."""

from __future__ import annotations

import json
import sqlite3
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from server.analyze.guard_scan import scan_instruction_events
from server.api.payloads import build_guard_analytics
from server.cli import app as cli_app
from server.store.migrate import migrate
from server.util.ids import new_ulid


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def _init_repo(root: Path) -> Path:
    repo = root / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "guard@example.com")
    _git(repo, "config", "user.name", "Guard Test")
    (repo / "AGENTS.md").write_text("# guide\n- first\n", encoding="utf-8")
    _git(repo, "add", "AGENTS.md")
    _git(repo, "commit", "-m", "add agents")
    (repo / "AGENTS.md").write_text("# guide\n- first\n- second\n", encoding="utf-8")
    _git(repo, "add", "AGENTS.md")
    _git(repo, "commit", "-m", "edit agents")
    return repo


def test_scan_records_instruction_edit(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    db = tmp_path / "cairn.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    since = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    until = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    result = scan_instruction_events(
        conn,
        workspace_id="ws",
        repo_root=repo,
        since=since,
        until=until,
    )
    assert result.upserted >= 1
    rows = conn.execute("SELECT event_kind, path_rel FROM guard_events").fetchall()
    assert any(row["event_kind"] == "edit" and row["path_rel"] == "AGENTS.md" for row in rows)
    conn.close()


def test_build_guard_analytics_no_git_is_explicit(tmp_path: Path) -> None:
    workspace = tmp_path / "plain"
    workspace.mkdir()
    db = tmp_path / "cairn.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    payload = build_guard_analytics(
        conn,
        workspace_id="ws",
        workspace_root=workspace,
        days=30,
    )
    assert payload.ledger.git_state == "no_git"
    assert any(event.event_kind == "unavailable" for event in payload.events)
    assert any("not a git repository" in note.lower() for note in payload.limitations)
    limitation = payload.ledger.limitation.lower()
    assert "not causal" in limitation or "association" in limitation
    conn.close()


def test_guard_api_shape(api_client: TestClient) -> None:
    resp = api_client.get("/api/analytics/guard?days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert "ledger" in body
    assert "events" in body
    assert "limitations" in body
    assert body["ledger"]["limitation"]
    assert set(body["ledger"]) >= {
        "conclusion",
        "event_count",
        "associated_count",
        "confounded_count",
        "git_state",
        "next_action",
        "limitation",
    }


def test_cairn_guard_cli(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ".cairn").mkdir()
    db = workspace / ".cairn" / "cairn.db"
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    ws_id = new_ulid()
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws_id, str(workspace), "guard-cli", datetime.now(UTC).isoformat()),
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("CAIRN_WORKSPACE", str(workspace))
    runner = CliRunner()
    result = runner.invoke(cli_app, ["guard", "--workspace", str(workspace), "--json"])
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["schema"] == "cairn.guard.v1"
    assert payload["generated_at"]
    assert "ledger" in payload
    assert "events" in payload
