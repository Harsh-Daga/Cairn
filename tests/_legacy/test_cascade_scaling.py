"""Phase 4 — cascade scaling and config tunables."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cairn.config import get_diagnose_setting, set_setting
from cairn.diagnose.cascade import detect_cascade


def test_cascade_default_k_is_three(monkeypatch, tmp_path: Path) -> None:
    cfg = tmp_path / ".config" / "cairn"
    cfg.mkdir(parents=True)
    monkeypatch.setattr("cairn.config.CONFIG_DIR", cfg)
    monkeypatch.setattr("cairn.config.CONFIG_PATH", cfg / "config.toml")
    assert int(get_diagnose_setting("cascade_k")) == 3


def test_cascade_respects_config_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    cfg = tmp_path / ".config" / "cairn"
    cfg.mkdir(parents=True)
    monkeypatch.setattr("cairn.config.CONFIG_DIR", cfg)
    monkeypatch.setattr("cairn.config.CONFIG_PATH", cfg / "config.toml")
    set_setting("diagnose", "cascade_k", 4)
    assert int(get_diagnose_setting("cascade_k")) == 4


def test_detect_cascade_large_session_under_budget() -> None:
    events = []
    for i in range(5000):
        events.append(
            {
                "event_id": i + 1,
                "seq": i + 1,
                "type": "tool_result" if i % 3 == 0 else "tool_call",
                "tool_is_error": 0,
                "waste_tokens": 0,
                "input_tokens": 10,
                "path_rel": "a.py",
                "args_hash": "h",
            }
        )
    start = time.perf_counter()
    root, blast, tokens = detect_cascade(events)
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert root is None
    assert elapsed_ms < 200, f"cascade took {elapsed_ms:.1f}ms"
