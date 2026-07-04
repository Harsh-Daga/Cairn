"""Tests for cairn check — environment checks and budget gates."""

from __future__ import annotations

import argparse
from pathlib import Path

from cairn.cli.main import cmd_check as run


def _args(**over: object) -> argparse.Namespace:
    base: dict[str, object] = {
        "project": Path("."),
        "json": False,
        "budget_usd": None,
        "budget_tokens": None,
        "max_waste_ratio": None,
        "min_quality": None,
        "days": None,
        "run": None,
        "format": "text",
    }
    base.update(over)
    return argparse.Namespace(**base)


def test_check_env_no_ledger(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    rc = run(_args(project=tmp_path))
    assert rc == 0


def test_check_env_with_ledger(tmp_path: Path, monkeypatch) -> None:
    from cairn.ledger.ledger import Ledger

    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    Ledger(db).close()
    monkeypatch.chdir(tmp_path)
    rc = run(_args(project=tmp_path))
    assert rc == 0


def test_check_json_output(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    rc = run(_args(project=tmp_path, json=True))
    assert rc == 0
    import json

    output = capsys.readouterr().out
    data = json.loads(output)
    assert isinstance(data, list)
    assert any("Ledger" in i.get("message", "") for i in data)


def test_check_budget_usd_under(tmp_path: Path, monkeypatch) -> None:
    from cairn.ingest.parsers.claude_code import parse_jsonl_file
    from cairn.ingest.writer import CaptureWriter
    from cairn.metrics.compute import backfill_session_metrics

    fixture = Path(__file__).parent / "fixtures" / "ingest" / "wasteful_session.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_jsonl_file(fixture, repo_root=root)
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_claude_session(parsed)
        backfill_session_metrics(writer, result.run_id)
    finally:
        writer.close()

    rc = run(_args(project=root, budget_usd=9999.0))
    assert rc == 0


def test_check_budget_usd_over(tmp_path: Path, monkeypatch) -> None:
    from cairn.ingest.parsers.claude_code import parse_jsonl_file
    from cairn.ingest.writer import CaptureWriter
    from cairn.metrics.compute import backfill_session_metrics

    fixture = Path(__file__).parent / "fixtures" / "ingest" / "wasteful_session.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_jsonl_file(fixture, repo_root=root)
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_claude_session(parsed)
        backfill_session_metrics(writer, result.run_id)
    finally:
        writer.close()

    import sqlite3

    conn = sqlite3.connect(str(root / ".cairn" / "ledger.db"))
    conn.execute("UPDATE runs SET total_cost = 5.0 WHERE run_id = ?", (result.run_id,))
    conn.commit()
    conn.close()

    rc = run(_args(project=root, budget_usd=0.001))
    assert rc == 1


def test_check_waste_ratio(tmp_path: Path, monkeypatch) -> None:
    from cairn.ingest.parsers.claude_code import parse_jsonl_file
    from cairn.ingest.writer import CaptureWriter
    from cairn.metrics.compute import backfill_session_metrics

    fixture = Path(__file__).parent / "fixtures" / "ingest" / "wasteful_session.jsonl"
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_jsonl_file(fixture, repo_root=root)
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_claude_session(parsed)
        backfill_session_metrics(writer, result.run_id)
    finally:
        writer.close()

    rc = run(_args(project=root, max_waste_ratio=0.001, days=3650))
    assert rc == 1

    rc = run(_args(project=root, max_waste_ratio=0.99, days=3650))
    assert rc == 0


def test_check_min_quality_pass(tmp_path: Path, monkeypatch) -> None:
    import sqlite3

    from cairn.ledger.schema import migrate

    root = tmp_path / "proj"
    root.mkdir()
    db = root / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, started_at, status, has_cost) "
        "VALUES ('r1', 'claude-code', 'e1', datetime('now'), 'completed', 0)"
    )
    conn.execute(
        "INSERT INTO outcomes (run_id, quality_score, captured_at) "
        "VALUES ('r1', 80.0, datetime('now'))"
    )
    conn.commit()
    conn.close()
    monkeypatch.chdir(root)
    assert run(_args(project=root, min_quality=70.0)) == 0


def test_check_min_quality_fail(tmp_path: Path, monkeypatch) -> None:
    import sqlite3

    from cairn.ledger.schema import migrate

    root = tmp_path / "proj"
    root.mkdir()
    db = root / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, started_at, status, has_cost) "
        "VALUES ('r1', 'claude-code', 'e1', datetime('now'), 'completed', 0)"
    )
    conn.execute(
        "INSERT INTO outcomes (run_id, quality_score, captured_at) "
        "VALUES ('r1', 40.0, datetime('now'))"
    )
    conn.commit()
    conn.close()
    monkeypatch.chdir(root)
    assert run(_args(project=root, min_quality=70.0)) == 1


def test_check_github_format_emits_error_lines(tmp_path: Path, monkeypatch, capsys) -> None:
    import re
    import sqlite3

    from cairn.ledger.schema import migrate

    root = tmp_path / "proj"
    root.mkdir()
    db = root / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, started_at, status, has_cost, total_cost) "
        "VALUES ('r1', 'claude-code', 'e1', datetime('now'), 'completed', 1, 5.0)"
    )
    conn.commit()
    conn.close()
    monkeypatch.chdir(root)
    rc_text = run(_args(project=root, budget_usd=0.001))
    capsys.readouterr()
    rc_github = run(_args(project=root, budget_usd=0.001, format="github"))
    out = capsys.readouterr().out
    assert rc_text == rc_github == 1
    assert re.search(r"^::error title=cairn check::", out, re.MULTILINE)


def test_check_github_format_silent_on_pass(tmp_path: Path, monkeypatch, capsys) -> None:
    from cairn.ledger.ledger import Ledger

    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True)
    Ledger(db).close()
    monkeypatch.chdir(tmp_path)
    rc = run(_args(project=tmp_path, format="github"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "::error" not in out
    assert "::warning" not in out


def test_api_action_check_returns_pass_and_reasons(tmp_path: Path, monkeypatch) -> None:
    import json
    from urllib.request import Request, urlopen

    from cairn.live.server import LiveServer

    monkeypatch.chdir(tmp_path)
    server = LiveServer(tmp_path, port=18795)
    server.serve_background()
    try:
        req = Request(
            f"{server.base_url}/api/action/check",
            data=b"{}",
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            data = json.loads(resp.read())
        assert "pass" in data
        assert isinstance(data["reasons"], list)
    finally:
        server.shutdown()


def test_api_action_check_min_quality_gate(tmp_path: Path, monkeypatch) -> None:
    import json
    import sqlite3
    from urllib.request import Request, urlopen

    from cairn.ledger.schema import migrate
    from cairn.live.server import LiveServer

    root = tmp_path / "proj"
    root.mkdir()
    db = root / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, external_id, started_at, status, has_cost) "
        "VALUES ('r1', 'claude-code', 'e1', datetime('now'), 'completed', 0)"
    )
    conn.execute(
        "INSERT INTO outcomes (run_id, quality_score, captured_at) "
        "VALUES ('r1', 40.0, datetime('now'))"
    )
    conn.commit()
    conn.close()
    monkeypatch.chdir(root)
    server = LiveServer(root, port=18796)
    server.serve_background()
    try:
        body = json.dumps({"min_quality": 70.0}).encode()
        req = Request(
            f"{server.base_url}/api/action/check",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req) as resp:
            data = json.loads(resp.read())
        assert data["pass"] is False
        assert any("Quality gate failed" in r for r in data["reasons"])
    finally:
        server.shutdown()


def test_cli_config_and_advanced_migrate_exist(tmp_path: Path) -> None:
    """`config get/set` and `advanced migrate` are registered and respond."""
    from tests.conftest import run_cairn

    assert run_cairn("config", "--help", cwd=tmp_path).returncode == 0
    assert run_cairn("advanced", "--help", cwd=tmp_path).returncode == 0
    assert run_cairn("config", "get", cwd=tmp_path).returncode == 0
