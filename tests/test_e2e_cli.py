"""End-to-end CLI smoke tests under RecordedProvider replay."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from cairn.cli.groups import ALL_COMMANDS
from tests.test_capture_phase5 import CLAUDE_FIXTURE


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cairn", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_help_lists_command_groups(tmp_path: Path) -> None:
    result = _run("help", "-v", cwd=tmp_path)
    assert result.returncode == 0
    assert "Project" in result.stdout
    assert "Capture" in result.stdout
    assert "snapshot" in result.stdout


def test_all_command_groups_registered() -> None:
    for cmd in ALL_COMMANDS:
        result = subprocess.run(
            [sys.executable, "-m", "cairn", cmd, "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, f"{cmd} --help failed: {result.stderr}"


def test_init_validate_status_build(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    assert _run("init", str(root), cwd=tmp_path).returncode == 0
    assert _run("validate", cwd=root).returncode == 0
    status = _run("status", cwd=root)
    assert status.returncode == 0
    assert "summaries:alpha" in status.stdout
    build = _run("build", "--yes", "--provider-mode", "recorded", cwd=root)
    assert build.returncode == 0
    assert "Run:" in build.stdout
    assert (root / "outputs" / "report.md").is_file()
    assert list((root / "runs").glob("*.json"))
    second = _run("build", "--yes", "--provider-mode", "recorded", cwd=root)
    assert second.returncode == 0
    assert "tokens=0" in second.stdout
    render = _run("render", "-o", str(root / "outputs" / "bundle"), "--zip", cwd=root)
    assert render.returncode == 0
    assert (root / "outputs" / "bundle" / "index.html").is_file()
    assert (root / "outputs" / "bundle.zip").is_file()


def test_capture_and_observability_cli(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    assert _run("init", str(root), cwd=tmp_path).returncode == 0

    claude_dir = tmp_path / "claude-sessions"
    claude_dir.mkdir()
    shutil.copy(CLAUDE_FIXTURE, claude_dir / "sess-redacted-001.jsonl")
    ingest = _run(
        "ingest",
        "--source",
        "claude-code",
        "--claude-project-dir",
        str(claude_dir),
        "--json",
        cwd=root,
    )
    assert ingest.returncode == 0
    ingest_payload = json.loads(ingest.stdout)
    assert ingest_payload[0]["inserted"] == 1

    sessions = _run("sessions", "list", "--json", cwd=root)
    assert sessions.returncode == 0
    payload = json.loads(sessions.stdout)
    assert any(s.get("session_id") == "sess-redacted-001" for s in payload)

    session_id = "sess-redacted-001"
    assert _run("show", session_id, "--json", cwd=root).returncode == 0
    assert _run("graph", session_id, "--kind", "execution", cwd=root).returncode == 0
    report = _run("report", "--session", session_id, "--json", cwd=root)
    assert report.returncode == 0
    assert json.loads(report.stdout)["kind"] == "capture"

    assert _run("artifact", "list", session_id, cwd=root).returncode == 0
    assert _run("context", "scan", cwd=root).returncode == 0
    assert _run("prompt", "sync", cwd=root).returncode == 0
    assert _run("workflow", "list", cwd=root).returncode == 0
    assert _run("collab", "status", cwd=root).returncode == 0

    snap = _run("snapshot", "create", "--label", "e2e", "--json", cwd=root)
    assert snap.returncode == 0
    assert _run("snapshot", "list", cwd=root).returncode == 0
