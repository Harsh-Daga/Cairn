"""Phase 12 unified report engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.report.engine import build_report, report_from_capture, report_from_provider
from cairn.report.schema import validate_report
from tests.test_capture_phase5 import CLAUDE_FIXTURE
from tests.test_invariants import _build


@pytest.fixture
def built_project(project_dir: Path, fixtures_dir: Path) -> Path:
    _build(project_dir, fixtures_dir)
    return project_dir


def test_capture_report_has_required_sections(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()

    report = report_from_capture(repo, parsed.external_id)
    assert report["cairn_report_version"] == 1
    assert report["kind"] == "capture"
    assert validate_report(report) == []
    assert report["summary"]["turn_count"] >= 1
    assert report["graphs"]["execution"]["graph_kind"] == "execution"
    assert report["graphs"]["artifact"]["graph_kind"] == "artifact"
    assert report["bundle"]["cairn_bundle_version"] == 3


def test_provider_report_has_required_sections(built_project: Path) -> None:
    report = report_from_provider(built_project)
    assert report["kind"] == "provider"
    assert validate_report(report) == []
    assert report["summary"]["node_count"] == 5
    assert report["graphs"]["dependency"]["graph_kind"] == "dependency"
    assert report["bundle"]["cairn_bundle_version"] == 1
    assert len(report["artifacts"]) >= 1


def test_build_report_rejects_both_selectors(built_project: Path) -> None:
    with pytest.raises(ValueError, match="not both"):
        build_report(built_project, session_id="x", run_id="y")


def test_build_report_defaults_to_latest_provider_run(built_project: Path) -> None:
    report = build_report(built_project)
    assert report["kind"] == "provider"
    assert validate_report(report) == []
