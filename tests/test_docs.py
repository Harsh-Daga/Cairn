"""Documentation consistency checks (Phase 21)."""

from __future__ import annotations

from pathlib import Path

from cairn.api.openapi import openapi_spec


def test_readme_covers_primary_workflows() -> None:
    text = (Path(__file__).parent.parent / "README.md").read_text(encoding="utf-8")
    for snippet in (
        "cairn ingest",
        "cairn live serve",
        "cairn api serve",
        "cairn workflow",
        "cairn report",
        "Project.open",
    ):
        assert snippet in text


def test_getting_started_and_api_docs_exist() -> None:
    root = Path(__file__).parent.parent
    assert (root / "docs" / "getting-started.md").is_file()
    assert (root / "docs" / "api.md").is_file()
    assert (root / "docs" / "security.md").is_file()


def test_openapi_matches_documented_routes() -> None:
    spec = openapi_spec()
    paths = spec["paths"]
    assert "/v1/projects/{project_id}/sessions" in paths
    assert "/v1/sessions/{session_id}" in paths
    assert "/v1/sessions/{session_id}/events" in paths
    assert "/v1/workflows/{workflow_id}/run" in paths
    assert "/v1/runs/{run_id}/report" in paths
