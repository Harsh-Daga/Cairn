"""Doctor preflight tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.doctor.checks import run_doctor
from cairn.loader.toml import load_project


def test_doctor_missing_credential(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OLLAMA_CLOUD_API_KEY", raising=False)
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace(
            "ollama-cloud/kimi-k2.6:cloud",
            "gpt-4o-mini",
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    project = load_project(project_dir)
    report = run_doctor(project)
    assert not report.ok
    assert any("missing credential" in i.message for i in report.issues)


def test_doctor_unknown_model(project_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "test-key")
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace(
            "ollama-cloud/kimi-k2.6:cloud",
            "ollama-cloud/not-a-real-model",
        ),
        encoding="utf-8",
    )
    project = load_project(project_dir)
    report = run_doctor(project)
    assert not report.ok
    assert any("unknown model" in i.message for i in report.issues)
