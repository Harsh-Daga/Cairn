"""Phase 18 public Python SDK tests."""

from __future__ import annotations

from pathlib import Path

import cairn
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.sdk.project import Run
from tests.test_capture_phase5 import CLAUDE_FIXTURE


def test_project_open(project_dir: Path) -> None:
    project = cairn.Project.open(project_dir)
    assert project.name == "my-cairn-project"
    assert project.root == project_dir.resolve()


def test_workflow_run_recorded(project_dir: Path) -> None:
    from cairn.workflow import run as workflow_run

    run = workflow_run(project=project_dir, yes=True, provider_mode="recorded")
    assert run.kind == "provider"
    assert run.run_id
    assert run.workflow_ref


def test_render_html_provider_run(project_dir: Path) -> None:
    from cairn.render import html as render_html
    from cairn.workflow import run as workflow_run

    run = workflow_run(project=project_dir, yes=True, provider_mode="recorded")
    out = project_dir / "outputs" / "sdk-bundle"
    index = render_html(run, output=out)
    assert index == out / "index.html"
    assert index.is_file()


def test_capture_run_and_report(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        result = writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    run = Run(
        project_root=repo,
        run_id=result.run_id,
        kind="capture",
        session_id=parsed.external_id,
    )
    from cairn.render import html as render_html
    from cairn.render import report_json

    report = report_json(run)
    assert report["kind"] == "capture"
    out = render_html(run, output=tmp_path / "cap-bundle")
    assert out.is_file()
