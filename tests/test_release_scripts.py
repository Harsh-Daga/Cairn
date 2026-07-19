"""Release identity and changelog extraction contracts."""

from __future__ import annotations

from subprocess import CompletedProcess

import pytest

from scripts.extract_release_notes import extract
from scripts.validate_release_tag import validate


def test_extract_release_notes_is_bounded_to_one_version() -> None:
    notes = extract("1.1.1")
    assert "Publish the 1.1 release" in notes
    assert "## [1.1.0]" not in notes


def test_release_tag_requires_exact_version_and_annotated_tag(monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.validate_release_tag.__version__",
        "1.2.0",
    )
    monkeypatch.setattr(
        "scripts.validate_release_tag.subprocess.run",
        lambda *_args, **_kwargs: CompletedProcess([], 0, stdout="tag\n"),
    )
    validate("v1.2.0")

    with pytest.raises(ValueError, match="does not match"):
        validate("v1.2.1")
    with pytest.raises(ValueError, match="vMAJOR"):
        validate("release-1.2.0")


def test_release_tag_rejects_lightweight_tag(monkeypatch) -> None:
    monkeypatch.setattr("scripts.validate_release_tag.__version__", "1.2.0")
    monkeypatch.setattr(
        "scripts.validate_release_tag.subprocess.run",
        lambda *_args, **_kwargs: CompletedProcess([], 0, stdout="commit\n"),
    )
    with pytest.raises(ValueError, match="annotated"):
        validate("v1.2.0")


def test_release_check_success_message_names_mode(capsys, monkeypatch) -> None:
    import scripts.release_check as release_check

    monkeypatch.setattr(release_check, "check_quality_gates", lambda **_kwargs: None)
    monkeypatch.setattr(release_check, "check_version_sync", lambda: None)
    monkeypatch.setattr(release_check, "check_changelog", lambda: None)
    monkeypatch.setattr(release_check, "check_readme_assets", lambda: None)
    monkeypatch.setattr(release_check, "check_readme_links", lambda: None)
    monkeypatch.setattr(release_check, "check_github_yaml", lambda: None)
    monkeypatch.setattr(release_check, "check_generated_artifacts", lambda: None)
    monkeypatch.setattr(release_check, "check_offline_static_assets", lambda: None)
    monkeypatch.setattr(release_check, "check_release_workflow", lambda: None)
    monkeypatch.setattr(release_check, "check_stale_packaging_text", lambda: None)
    monkeypatch.setattr(release_check, "check_doctor_on_wheel", lambda: None)
    monkeypatch.setattr(release_check, "check_reproducibility_assessment", lambda: None)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

    assert release_check.main(["--packaging-only"]) == 0
    assert "packaging-only" in capsys.readouterr().out

    assert release_check.main([]) == 0
    assert "full gate" in capsys.readouterr().out


def test_release_check_forbids_skip_flags_in_ci(monkeypatch) -> None:
    import scripts.release_check as release_check

    monkeypatch.setenv("CI", "true")
    with pytest.raises(SystemExit, match="CI forbids"):
        release_check.main(["--skip-e2e"])
