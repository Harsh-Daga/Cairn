"""Git privacy: ignore detection, exclude approval, tracked-path warnings."""

from __future__ import annotations

import subprocess
from pathlib import Path

from server.analyze.git_privacy import (
    assess_git_privacy,
    ensure_git_exclude_cairn,
    exclude_has_cairn,
    export_path_warnings,
)
from server.doctor import run_doctor


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "README").write_text("x\n", encoding="utf-8")
    _git(path, "add", "README")
    _git(path, "commit", "-m", "init")
    return path


def test_not_a_git_repo_is_ok(tmp_path: Path) -> None:
    root = tmp_path / "plain"
    root.mkdir()
    report = assess_git_privacy(root)
    assert report.is_git_repo is False
    assert report.kind == "ok"


def test_exclude_approval_is_idempotent(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "repo")
    denied = ensure_git_exclude_cairn(repo, approve=False)
    assert denied["ok"] is False
    first = ensure_git_exclude_cairn(repo, approve=True)
    assert first["ok"] is True
    assert first["changed"] is True
    assert exclude_has_cairn(repo)
    second = ensure_git_exclude_cairn(repo, approve=True)
    assert second["ok"] is True
    assert second["changed"] is False
    report = assess_git_privacy(repo)
    assert report.kind == "ok"


def test_tracked_cairn_path_is_attention(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "tracked")
    cairn = repo / ".cairn"
    cairn.mkdir()
    (cairn / "leak.txt").write_text("secret\n", encoding="utf-8")
    _git(repo, "add", "-f", ".cairn/leak.txt")
    _git(repo, "commit", "-m", "track cairn")
    report = assess_git_privacy(repo)
    assert report.kind == "attention"
    assert report.tracked_paths
    doctor = run_doctor(workspace=repo)
    git_check = next(item for item in doctor if item.name == "Git privacy")
    assert git_check.ok is False


def test_export_warning_when_destination_tracked(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path / "export")
    tracked = repo / "public"
    tracked.mkdir()
    (tracked / "keep.txt").write_text("ok\n", encoding="utf-8")
    _git(repo, "add", "public/keep.txt")
    _git(repo, "commit", "-m", "track public")
    warnings = export_path_warnings(repo, tracked / "bundle.json")
    assert any("tracked" in item.lower() for item in warnings)
