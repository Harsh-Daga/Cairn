"""Tests for cairn doctor."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.doctor import (
    _check_adapter_health,
    _check_database_integrity,
    _check_mcp_config,
    _check_permissions,
    run_doctor,
)
from server.ingest.parse_health import record_parse_attempt
from server.store.db import connect
from server.store.migrate import migrate


def test_doctor_runs_all_checks() -> None:
    results = run_doctor()
    names = {r.name for r in results}
    assert "Python >=3.11" in names
    assert "Static UI assets" in names
    assert "Adapters detected" in names
    assert "Adapter parse health" in names
    assert "Private file permissions" in names


def test_doctor_python_passes() -> None:
    results = run_doctor()
    python = next(r for r in results if r.name == "Python >=3.11")
    assert python.ok


def test_doctor_mcp_config_is_advisory_when_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("server.doctor.Path.home", lambda: tmp_path)
    result = _check_mcp_config()
    assert result.ok
    assert "optional" in result.detail


def test_doctor_warns_on_adapter_parse_degradation(tmp_path: Path) -> None:
    db_path = tmp_path / ".cairn" / "cairn.db"
    conn = connect(db_path)
    migrate(conn)
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        ("ws", str(tmp_path), "test", "2026-01-01T00:00:00Z"),
    )
    record_parse_attempt(
        conn,
        workspace_id="ws",
        adapter_id="codex",
        outcome="degraded",
        unknown_fields={"new_payload": 4},
    )
    conn.commit()
    conn.close()

    result = _check_adapter_health(tmp_path)

    assert result.ok is False
    assert "codex log format may have changed" in result.detail
    assert result.fix is not None and "issues/new" in result.fix


def test_doctor_detects_and_repairs_permissive_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if __import__("os").name == "nt":
        pytest.skip("Unix mode test")
    home = tmp_path / "home"
    workspace = tmp_path / "workspace"
    private_dir = workspace / ".cairn"
    home.mkdir()
    private_dir.mkdir(parents=True, mode=0o755)
    database = private_dir / "cairn.db"
    database.write_text("private", encoding="utf-8")
    private_dir.chmod(0o755)
    database.chmod(0o644)
    monkeypatch.setattr("server.doctor.Path.home", lambda: home)

    detected = _check_permissions(workspace)
    repaired = _check_permissions(workspace, repair=True)

    assert detected.ok is False
    assert detected.fix == "Run: cairn doctor --repair-permissions"
    assert repaired.ok is True
    assert private_dir.stat().st_mode & 0o777 == 0o700
    assert database.stat().st_mode & 0o777 == 0o600


def test_doctor_reports_corrupt_database_without_modifying_it(tmp_path: Path) -> None:
    db_path = tmp_path / ".cairn" / "cairn.db"
    db_path.parent.mkdir()
    original = b"not a sqlite database"
    db_path.write_bytes(original)

    result = _check_database_integrity(tmp_path)

    assert result.ok is False
    assert "corrupt" in result.detail
    assert db_path.read_bytes() == original


def test_doctor_reports_foreign_key_inconsistency_read_only(tmp_path: Path) -> None:
    db_path = tmp_path / ".cairn" / "cairn.db"
    conn = connect(db_path)
    migrate(conn)
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute(
        """
        INSERT INTO spans (span_id, trace_id, seq, kind, status)
        VALUES ('orphan-span', 'missing-trace', 1, 'tool_call', 'ok')
        """
    )
    conn.commit()
    conn.close()
    before = db_path.read_bytes()

    result = _check_database_integrity(tmp_path)

    assert result.ok is False
    assert "foreign_key_check" in result.detail
    assert db_path.read_bytes() == before
