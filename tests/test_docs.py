"""Documentation consistency checks."""

from __future__ import annotations

from pathlib import Path

import cairn
from cairn.api.openapi import openapi_spec

ROOT = Path(__file__).parent.parent


def test_readme_covers_primary_workflows() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for snippet in (
        "cairn ingest",
        "cairn live serve",
        "cairn api serve",
        "cairn workflow",
        "cairn report",
        "Project.open",
        "pip install cairn-workspace",
        "pypi.org/project/cairn-workspace",
        "curl -fsSL",
    ):
        assert snippet in text


def test_user_documentation_exists() -> None:
    for rel in (
        "docs/README.md",
        "docs/getting-started.md",
        "docs/concepts.md",
        "docs/guides/e2e-testing.md",
        "docs/guides/provider-workflows.md",
        "docs/guides/agent-capture.md",
        "docs/reference/cli.md",
        "docs/reference/configuration.md",
        "docs/reference/sdk.md",
        "docs/reference/api.md",
        "docs/security.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "examples/e2e-demo/setup.sh",
    ):
        assert (ROOT / rel).is_file(), rel


def test_internal_planning_docs_removed() -> None:
    for rel in (
        "PROGRESS.md",
        "docs/architecture-audit.md",
        "docs/phase-0-vision-validation.md",
        "docs/engineering-reference-legacy.md",
        "CHARTER.md",
        "docs/adr",
    ):
        assert not (ROOT / rel).exists(), f"obsolete doc still present: {rel}"
    assert (ROOT / "docs" / "spec" / "charter.md").is_file()


def test_release_version_matches_pyproject() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.1.0"' in pyproject
    assert cairn.__version__ == "1.1.0"


def test_openapi_matches_documented_routes() -> None:
    spec = openapi_spec()
    paths = spec["paths"]
    assert "/v1/projects/{project_id}/sessions" in paths
    assert "/v1/sessions/{session_id}" in paths
    assert "/v1/sessions/{session_id}/events" in paths
    assert "/v1/workflows/{workflow_id}/run" in paths
    assert "/v1/runs/{run_id}/report" in paths
