"""End-to-end CLI smoke tests for the 7-command surface."""

from __future__ import annotations

import shutil
from pathlib import Path

from cairn.cli.main import ALL_COMMANDS
from tests.conftest import run_cairn
from tests.test_cursor_capture import CLAUDE_FIXTURE


def test_help_shows_seven_command_surface(tmp_path: Path) -> None:
    result = run_cairn("help", cwd=tmp_path)
    assert result.returncode == 0
    assert "Everyday" in result.stdout
    assert "Data" in result.stdout
    assert "CI" in result.stdout
    for cmd in ALL_COMMANDS:
        assert cmd in result.stdout


def test_all_commands_registered() -> None:
    for cmd in ALL_COMMANDS:
        result = run_cairn(cmd, "--help")
        assert result.returncode == 0, f"{cmd} --help failed: {result.stderr}"


def test_old_commands_redirect_via_aliases(tmp_path: Path) -> None:
    old_commands = ("ingest", "sessions", "render")
    for old_cmd in old_commands:
        result = run_cairn(old_cmd, "--help", cwd=tmp_path)
        assert result.returncode == 0, f"alias {old_cmd} failed: {result.stderr}"
        assert "note:" in result.stderr


def test_sync_and_show(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    root.mkdir()

    claude_dir = tmp_path / "claude-sessions"
    claude_dir.mkdir()
    shutil.copy(CLAUDE_FIXTURE, claude_dir / "sess-redacted-001.jsonl")

    ingest = run_cairn(
        "sync",
        "--source",
        "claude-code",
        "--claude-project-dir",
        str(claude_dir),
        cwd=root,
    )
    assert ingest.returncode == 0

    show = run_cairn("show", cwd=root)
    assert show.returncode == 0
