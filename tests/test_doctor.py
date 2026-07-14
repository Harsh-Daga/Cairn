"""Tests for cairn doctor."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.doctor import _check_adapter_health, _check_mcp_config, run_doctor
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
