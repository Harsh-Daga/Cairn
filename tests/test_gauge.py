"""Tests for the plan-window gauge (5-hour rolling token consumption)."""

from __future__ import annotations

from pathlib import Path

import cairn.config as userconfig_mod
from cairn.config import UserConfig, save_user_config
from cairn.context.gauge import compute_gauge
from cairn.ledger.ledger import Ledger


def test_gauge_no_ledger(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    gauge = compute_gauge(root)
    assert gauge.total_tokens == 0
    assert not gauge.exceeded


def test_gauge_with_limit_not_exceeded(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    monkeypatch.setattr(userconfig_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(userconfig_mod, "CONFIG_PATH", config_file)

    cfg = UserConfig(five_hour_tokens=100000)
    save_user_config(cfg)

    root = tmp_path / "proj"
    root.mkdir()
    (root / ".cairn").mkdir()

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        conn.execute(
            """
            INSERT INTO runs (run_id, source, external_id, started_at, ended_at,
                status, total_input_tokens, total_output_tokens, has_cost)
            VALUES (?, 'claude-code', ?, datetime('now'), datetime('now'),
                    'completed', 500, 100, 1)
            """,
            ("r1", "s1"),
        )
        conn.commit()
    finally:
        ledger.close()

    gauge = compute_gauge(root)
    assert gauge.limit == 100000
    assert not gauge.exceeded
    assert "claude-code" in gauge.by_source


def test_gauge_with_limit_exceeded(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "cfg"
    config_dir.mkdir()
    config_file = config_dir / "config.toml"
    monkeypatch.setattr(userconfig_mod, "CONFIG_DIR", config_dir)
    monkeypatch.setattr(userconfig_mod, "CONFIG_PATH", config_file)

    cfg = UserConfig(five_hour_tokens=10)
    save_user_config(cfg)

    root = tmp_path / "proj"
    root.mkdir()
    (root / ".cairn").mkdir()

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        conn = ledger.connection
        conn.execute(
            """
            INSERT INTO runs (run_id, source, external_id, started_at, ended_at,
                status, total_input_tokens, total_output_tokens, has_cost)
            VALUES (?, 'claude-code', ?, datetime('now'), datetime('now'),
                    'completed', 5000, 1000, 1)
            """,
            ("r1", "s1"),
        )
        conn.commit()
    finally:
        ledger.close()

    gauge = compute_gauge(root)
    assert gauge.limit == 10
    assert gauge.exceeded
    assert gauge.total_tokens > 10
