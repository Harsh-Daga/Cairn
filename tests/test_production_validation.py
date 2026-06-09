"""Phase 22 production validation — full user journey (provider + capture)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import cairn
from cairn.api.openapi import openapi_spec
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.render import html as render_html
from cairn.render import report_json
from cairn.sdk.project import Run
from cairn.workflow import run as workflow_run
from tests.test_capture_phase5 import CLAUDE_FIXTURE


def _run_env() -> dict[str, str]:
    return {**os.environ, "OLLAMA_CLOUD_API_KEY": "test-key"}


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cairn", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=_run_env(),
    )


def test_release_version_is_1_0_0() -> None:
    assert cairn.__version__ == "1.0.0"
    result = subprocess.run(
        [sys.executable, "-m", "cairn", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "cairn 1.0.0" in result.stdout


def test_full_user_journey_provider_then_capture(tmp_path: Path) -> None:
    """Init → build → render → ingest → observe → snapshot → SDK → API spec."""
    root = tmp_path / "workspace"
    assert _run("init", str(root), cwd=tmp_path).returncode == 0
    assert _run("validate", cwd=root).returncode == 0
    assert _run("doctor", cwd=root).returncode == 0

    build = _run("build", "--yes", "--provider-mode", "recorded", cwd=root)
    assert build.returncode == 0
    assert (root / "outputs" / "report.md").is_file()

    bundle_dir = root / "outputs" / "provider-bundle"
    render = _run("render", "-o", str(bundle_dir), "--zip", cwd=root)
    assert render.returncode == 0
    assert (bundle_dir / "index.html").is_file()
    assert (root / "outputs" / "provider-bundle.zip").is_file()

    report = _run("report", "--json", cwd=root)
    assert report.returncode == 0
    assert json.loads(report.stdout)["kind"] == "provider"

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
    session_id = "sess-redacted-001"

    assert _run("sessions", "list", cwd=root).returncode == 0
    assert _run("show", session_id, "--json", cwd=root).returncode == 0
    assert _run("graph", session_id, "--kind", "execution", cwd=root).returncode == 0
    cap_report = _run("report", "--session", session_id, "--json", cwd=root)
    assert cap_report.returncode == 0
    assert json.loads(cap_report.stdout)["kind"] == "capture"

    cap_bundle = root / "outputs" / "capture-bundle"
    assert _run("render", "--session", session_id, "-o", str(cap_bundle), cwd=root).returncode == 0
    assert (cap_bundle / "index.html").is_file()

    snap = _run("snapshot", "create", "--label", "release", "--json", cwd=root)
    assert snap.returncode == 0
    assert _run("snapshot", "list", cwd=root).returncode == 0
    assert _run("collab", "status", cwd=root).returncode == 0

    project = cairn.Project.open(root)

    sdk_run = workflow_run(project=project, yes=True, provider_mode="recorded")
    sdk_report = report_json(sdk_run)
    assert sdk_report["kind"] == "provider"
    sdk_out = render_html(sdk_run, output=root / "outputs" / "sdk-bundle")
    assert sdk_out.is_file()

    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=root)
    assert parsed is not None
    writer = CaptureWriter(root)
    try:
        cap = writer.ingest_claude_session(parsed)
    finally:
        writer.close()
    cap_run = Run(
        project_root=root,
        run_id=cap.run_id,
        kind="capture",
        session_id=session_id,
    )
    assert report_json(cap_run)["kind"] == "capture"

    spec = openapi_spec()
    assert "/v1/openapi.json" not in spec["paths"]
    assert "/v1/sessions/{session_id}/events" in spec["paths"]


def test_spike_directory_removed() -> None:
    assert not (Path(__file__).parent.parent / "spike").exists()
