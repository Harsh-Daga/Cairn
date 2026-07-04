"""Phase A: source detection and empty-state guidance."""

from __future__ import annotations

import argparse
from pathlib import Path

import cairn.ingest.detect as detect_mod
from cairn.cli.main import _print_empty_state
from cairn.cli.main import cmd_default as default_run


def test_detect_sources_returns_list(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    sources = detect_mod.detect_sources(repo)
    assert isinstance(sources, list)


def test_empty_state_prints_escape_hatch(capsys) -> None:
    _print_empty_state(Path("/tmp/x"))
    out = capsys.readouterr().out
    assert "--claude-project-dir" in out
    assert "No agent history found" in out
    assert "guided setup" in out


def test_bare_run_no_history_is_clean(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(detect_mod, "detect_sources", lambda root: [])
    import cairn.cli.main as dc

    monkeypatch.setattr(dc, "detect_sources", lambda root: [])
    monkeypatch.setattr(dc, "start_dashboard", lambda *a, **k: 0)

    args = argparse.Namespace(
        project=tmp_path,
        source=None,
        since=None,
        port=8787,
        no_open=True,
        foreground=False,
        global_view=False,
    )
    rc = default_run(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "No agent history found" in out
