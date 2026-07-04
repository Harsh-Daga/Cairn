"""Phase A: the 7-command surface and alias redirects."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from cairn.cli.main import ALIASES, ALL_COMMANDS, COMMAND_GROUPS
from tests.conftest import ROOT, run_cairn


def _cli_env(tmp_path: Path) -> dict[str, str]:
    return {"CAIRN_STATE_DIR": str(tmp_path / "cairn-state")}


def test_help_shows_the_seven_command_surface(tmp_path: Path) -> None:
    result = run_cairn("help", cwd=tmp_path)
    assert result.returncode == 0
    for group in COMMAND_GROUPS:
        assert group in result.stdout
    for cmd in ALL_COMMANDS:
        assert cmd in result.stdout
    assert "golden path" in result.stdout
    assert "background" in result.stdout
    assert "\n    ls" not in result.stdout


def test_visible_commands_have_help(tmp_path: Path) -> None:
    for cmd in ALL_COMMANDS:
        result = run_cairn(cmd, "--help", cwd=tmp_path)
        assert result.returncode == 0, f"{cmd} --help failed: {result.stderr}"


def test_every_alias_redirects_with_note(tmp_path: Path) -> None:
    for old_cmd in ALIASES:
        result = run_cairn(old_cmd, "--help", cwd=tmp_path)
        assert "note:" in result.stderr, f"alias {old_cmd} printed no redirect note"


def test_bare_cairn_in_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    env = _cli_env(tmp_path)
    result = run_cairn("--no-open", cwd=repo, env=env)
    assert result.returncode == 0
    assert "background" in result.stdout or "already running" in result.stdout
    run_cairn("stop", cwd=repo, env=env)


def test_bare_cairn_global_mode_non_repo(tmp_path: Path) -> None:
    plain = tmp_path / "not-a-repo"
    plain.mkdir()
    env = _cli_env(tmp_path)
    result = run_cairn("--no-open", "--port", "18788", cwd=plain, env=env)
    assert result.returncode == 0
    run_cairn("stop", "--port", "18788", cwd=plain, env=env)


def test_foreground_flag_accepted(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["CAIRN_STATE_DIR"] = str(tmp_path / "fg-state")
    proc = subprocess.Popen(
        [sys.executable, "-m", "cairn", "--foreground", "--no-open", "--port", "18787"],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)
        assert proc.returncode in (0, -15, None)
    else:
        assert proc.returncode == 0


def test_background_launch_uses_spawn_daemon(tmp_path: Path) -> None:
    import argparse

    from cairn.cli.main import cmd_default

    repo = tmp_path / "repo"
    repo.mkdir()
    args = argparse.Namespace(
        project=repo,
        source=None,
        since=None,
        port=18789,
        no_open=True,
        foreground=False,
        global_view=False,
    )
    with patch("cairn.cli.main._spawn_daemon", return_value=4242) as spawn:
        rc = cmd_default(args)
    assert rc == 0
    spawn.assert_called_once()


def test_stop_without_pid_file(tmp_path: Path) -> None:
    env = _cli_env(tmp_path)
    result = run_cairn("stop", cwd=tmp_path, env=env)
    assert result.returncode == 0
    assert "No background Cairn server running" in result.stdout
