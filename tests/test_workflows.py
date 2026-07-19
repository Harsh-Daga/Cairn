"""Static invariants for deterministic, least-privilege GitHub workflows."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
PINNED_ACTION = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def _documents() -> dict[Path, dict[str, object]]:
    return {
        path: yaml.safe_load(path.read_text(encoding="utf-8"))
        for path in sorted(WORKFLOWS.glob("*.yml"))
    }


def test_every_external_action_is_pinned_to_a_full_commit() -> None:
    for path, document in _documents().items():
        jobs = document.get("jobs", {})
        assert isinstance(jobs, dict)
        for job in jobs.values():
            assert isinstance(job, dict)
            steps = job.get("steps", [])
            assert isinstance(steps, list)
            for step in steps:
                assert isinstance(step, dict)
                action = step.get("uses")
                if action is not None:
                    assert isinstance(action, str)
                    assert PINNED_ACTION.fullmatch(action), f"{path.name}: {action}"


def test_ci_contains_required_deterministic_gates() -> None:
    text = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
    for version in ('"3.11"', '"3.12"', '"3.13"'):
        assert version in text
    for command in (
        "uv sync --frozen",
        "uv run ruff check .",
        "uv run ruff format --check .",
        "uv run mypy --strict server",
        "uv run pytest",
        "npm ci",
        "npm run lint",
        "npm run format:check",
        "npm run typecheck",
        "npm test",
        "npm run test:coverage",
        "npm run check:api",
        "npm run test:e2e",
        "scripts/check_bundle_size.py",
        "scripts/check_coverage.py",
    ):
        assert command in text
    assert "npm install" not in text
    assert "cancel-in-progress: true" in text
    assert "playwright install --with-deps chromium firefox webkit" in text
    playwright = (ROOT / "ui" / "playwright.config.ts").read_text(encoding="utf-8")
    for project in ('name: "chromium"', 'name: "firefox"', 'name: "webkit"'):
        assert project in playwright
    assert "grep: /@cross-browser/" in playwright


def test_noisy_performance_timings_are_scheduled_or_manual_artifacts() -> None:
    text = (WORKFLOWS / "performance.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "schedule:" in text
    assert "pull_request:" not in text
    assert "scripts/benchmark.py run" in text
    assert "--profile large" in text
    assert "--include-static" in text
    assert "actions/upload-artifact@" in text


def test_workflows_declare_permissions() -> None:
    for path, document in _documents().items():
        assert "permissions" in document, f"{path.name} has implicit token permissions"


def test_security_workflow_has_required_scanners_and_safe_pr_boundary() -> None:
    text = (WORKFLOWS / "security.yml").read_text(encoding="utf-8")
    for required in (
        "github/codeql-action/init@",
        "language: [python, javascript-typescript]",
        "actions/dependency-review-action@",
        "uv run pip-audit",
        "npm audit --audit-level=moderate",
        "ossf/scorecard-action@",
        "github/codeql-action/upload-sarif@",
    ):
        assert required in text
    dependency_job = text.split("dependency-review:", maxsplit=1)[1].split(
        "vulnerability-audit:", maxsplit=1
    )[0]
    assert "contents: read" in dependency_job
    assert "id-token: write" not in dependency_job


def test_release_builds_once_and_publishes_only_tested_artifacts() -> None:
    text = (WORKFLOWS / "publish.yml").read_text(encoding="utf-8")
    assert "branches:" not in text
    assert 'tags: ["v*"]' in text
    assert "scripts/validate_release_tag.py" in text
    assert "uv build --out-dir release-artifacts/packages" in text
    assert text.count("uv build ") == 1
    assert "needs: build" in text
    assert "needs: verify" in text
    assert "needs: publish" in text
    assert "pypa/gh-action-pypi-publish@" in text
    assert "actions/attest-build-provenance@" in text
    assert "SHA256SUMS" in text
    assert "cyclonedx-json" in text
    assert "environment: pypi" in text
    assert 'uvx --refresh --from "cairn-workspace==${VERSION}"' in text
