"""Dashboard startup — project-root handoff and cache headers."""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

import pytest

from cairn.cli import main as cli_main
from cairn.live.server import LiveServer


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_needs_dashboard_restart_via_api_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    existing = {"port": 8787, "pid": 42, "root": str(a)}
    monkeypatch.setattr(cli_main, "_we_own_dashboard", lambda port: True)
    monkeypatch.setattr(cli_main, "_server_project_root", lambda port: str(a))
    assert cli_main._needs_dashboard_restart(existing, b, 8787) is True
    assert cli_main._needs_dashboard_restart(existing, a, 8787) is False


def test_needs_dashboard_restart_when_not_owner(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    existing = {"port": 8787, "pid": None}
    monkeypatch.setattr(cli_main, "_we_own_dashboard", lambda port: False)
    assert cli_main._needs_dashboard_restart(existing, root, 8787) is True


def test_kill_port_listener_terminates_process(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, int]] = []
    state = {"pid": 4242}

    def fake_listener(port: int) -> int | None:
        return state["pid"]

    def fake_kill(pid: int, sig: int) -> None:
        calls.append((pid, sig))
        state["pid"] = None

    monkeypatch.setattr(cli_main, "_port_listener_pid", fake_listener)
    monkeypatch.setattr(cli_main.os, "kill", fake_kill)
    assert cli_main._kill_port_listener(8787) is True
    assert calls and calls[0][0] == 4242


def test_start_dashboard_restarts_on_root_change(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    calls: list[str] = []

    monkeypatch.setattr(
        cli_main, "_running_server", lambda port: {"pid": 42, "port": port, "root": str(a)}
    )
    monkeypatch.setattr(cli_main, "_we_own_dashboard", lambda p: False)
    monkeypatch.setattr(cli_main, "_needs_dashboard_restart", lambda e, r, p: True)
    monkeypatch.setattr(cli_main, "_stop_dashboard_on_port", lambda p: calls.append("stop") or True)
    monkeypatch.setattr(cli_main, "_spawn_daemon", lambda r, p: calls.append(f"spawn:{r}") or 99)
    monkeypatch.setattr(cli_main, "_notify_dashboard_refresh", lambda p: True)
    monkeypatch.setattr(
        cli_main, "_open_dashboard", lambda url, no_open=False: calls.append("open")
    )

    rc = cli_main.start_dashboard(b, port=8787, no_open=True)
    assert rc == 0
    assert "stop" in calls
    assert any(c.startswith("spawn:") for c in calls)


def test_api_responses_have_no_store_header(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    port = _free_port()
    server = LiveServer(repo, port=port)
    server.serve_background()
    try:
        with urllib.request.urlopen(f"{server.base_url}/api/overview?days=7", timeout=5) as resp:
            assert resp.headers.get("Cache-Control") == "no-store"
            body = json.loads(resp.read())
        assert "kpis" in body
        assert "narrative" in body
        assert body["narrative"].get("headline") is not None
        assert "diagnostics_summary" in body
    finally:
        server.shutdown()


def test_api_session_includes_diagnostics_keys(tmp_path: Path) -> None:
    from cairn.ledger.schema import migrate

    repo = tmp_path / "proj"
    repo.mkdir()
    db = repo / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = __import__("sqlite3").connect(db)
    conn.row_factory = __import__("sqlite3").Row
    migrate(conn)
    now = __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, project, started_at, status,
          total_cost, total_input_tokens, total_output_tokens, has_cost, event_count
        ) VALUES ('srv-diag', 'claude-code', 'e1', 'proj', ?, 'completed',
                  1.0, 1000, 200, 1, 2)
        """,
        (now,),
    )
    conn.execute(
        """
        INSERT INTO events (run_id, seq, type, role) VALUES ('srv-diag', 1, 'user_prompt', 'user')
        """
    )
    conn.execute(
        """
        INSERT INTO diagnostics (
          run_id, outcome_label, label_source, failure_origin_event_id,
          primary_category, cascade_root_event_id, cascade_blast_tokens,
          ideal_path_savings_tokens, computed_at
        ) VALUES ('srv-diag', 'partial', 'deterministic', 1, 'test_neglect',
                  1, 500, 100, ?)
        """,
        (now,),
    )
    conn.commit()
    conn.close()

    port = _free_port()
    server = LiveServer(repo, port=port)
    server.serve_background()
    try:
        with urllib.request.urlopen(f"{server.base_url}/api/session/srv-diag", timeout=5) as resp:
            body = json.loads(resp.read())
        assert body.get("diagnostics") is not None
        assert "failure_origin_event_id" in body
        assert "cascade_root_event_id" in body
        assert body.get("ideal_path") is not None
    finally:
        server.shutdown()


def test_open_dashboard_adds_cache_bust(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(cli_main.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(cli_main.time, "time", lambda: 1234567890)
    cli_main._open_dashboard("http://127.0.0.1:8787", no_open=False)
    assert opened == ["http://127.0.0.1:8787/?_=1234567890"]
