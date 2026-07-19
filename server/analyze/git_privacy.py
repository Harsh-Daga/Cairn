"""Git privacy helpers: ignore status, tracked Cairn paths, exclude approval."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from server.analyze.git_local import is_git_repo, run_git

EXCLUDE_MARKER = "# Cairn local observability data (added by cairn git_exclude)"
EXCLUDE_ENTRY = ".cairn/"


@dataclass(frozen=True, slots=True)
class GitPrivacyReport:
    kind: Literal["not_a_git_repo", "ok", "attention"]
    is_git_repo: bool
    cairn_ignored: bool | None
    tracked_paths: list[str]
    exclude_path: str | None
    exclude_has_entry: bool
    message: str
    limitation: str


def git_toplevel(workspace_root: Path) -> Path | None:
    """Return the git work tree root containing workspace_root, if any."""
    root = workspace_root.resolve()
    if not is_git_repo(root):
        # Walk up for nested paths that aren't the repo root themselves.
        current = root
        for _ in range(12):
            if ((current / ".git").exists() or (current / ".git").is_file()) and is_git_repo(
                current
            ):
                return current
            if current.parent == current:
                break
            current = current.parent
        return None
    result = run_git(root, ["git", "rev-parse", "--show-toplevel"])
    if result is None or result.returncode != 0:
        return root
    text = result.stdout.strip()
    return Path(text) if text else root


def path_is_ignored(repo: Path, relative: str) -> bool | None:
    """Return whether path is ignored; None if git check-ignore is unavailable."""
    result = run_git(repo, ["git", "check-ignore", "-q", "--", relative])
    if result is None:
        return None
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    return None


def tracked_cairn_paths(repo: Path) -> list[str]:
    """List tracked paths under .cairn/ (should normally be empty)."""
    result = run_git(repo, ["git", "ls-files", "--", ".cairn", ".cairn/**"])
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def path_is_tracked(repo: Path, path: Path) -> bool:
    """True if path (file or under a tracked prefix) is in the git index."""
    try:
        rel = path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return False
    result = run_git(repo, ["git", "ls-files", "--error-unmatch", "--", rel])
    return bool(result and result.returncode == 0)


def resolve_git_dir(repo: Path) -> Path | None:
    """Resolve `.git` directory, including worktree gitfile pointers."""
    git_path = repo / ".git"
    if git_path.is_dir():
        return git_path
    if git_path.is_file():
        try:
            text = git_path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        if text.startswith("gitdir:"):
            return (repo / text.split(":", 1)[1].strip()).resolve()
    return None


def exclude_file(repo: Path) -> Path:
    git_dir = resolve_git_dir(repo) or (repo / ".git")
    return git_dir / "info" / "exclude"


def exclude_has_cairn(repo: Path) -> bool:
    path = exclude_file(repo)
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped in {".cairn/", ".cairn", "**/.cairn/"}:
            return True
    return False


def assess_git_privacy(workspace_root: Path) -> GitPrivacyReport:
    """Doctor/privacy-facing assessment (never mutates git state)."""
    limitation = (
        "Uses local git only (check-ignore / ls-files / info/exclude). "
        "Bare repos and missing git binary are reported as unavailable, not healthy."
    )
    repo = git_toplevel(workspace_root)
    if repo is None:
        return GitPrivacyReport(
            kind="ok",
            is_git_repo=False,
            cairn_ignored=None,
            tracked_paths=[],
            exclude_path=None,
            exclude_has_entry=False,
            message="Workspace is not inside a git work tree; no tracked-data risk from git.",
            limitation=limitation,
        )
    ignored = path_is_ignored(repo, ".cairn/")
    if ignored is None:
        ignored = path_is_ignored(repo, ".cairn")
    tracked = tracked_cairn_paths(repo)
    has_exclude = exclude_has_cairn(repo)
    if tracked:
        return GitPrivacyReport(
            kind="attention",
            is_git_repo=True,
            cairn_ignored=ignored,
            tracked_paths=tracked[:20],
            exclude_path=str(exclude_file(repo)),
            exclude_has_entry=has_exclude,
            message=(
                f"{len(tracked)} Cairn path(s) are already tracked by git "
                f"(e.g. {tracked[0]}). Untrack before committing."
            ),
            limitation=limitation,
        )
    if ignored is True or has_exclude:
        return GitPrivacyReport(
            kind="ok",
            is_git_repo=True,
            cairn_ignored=True if ignored is True else ignored,
            tracked_paths=[],
            exclude_path=str(exclude_file(repo)),
            exclude_has_entry=has_exclude,
            message=".cairn/ is ignored (gitignore or .git/info/exclude).",
            limitation=limitation,
        )
    return GitPrivacyReport(
        kind="attention",
        is_git_repo=True,
        cairn_ignored=False if ignored is False else ignored,
        tracked_paths=[],
        exclude_path=str(exclude_file(repo)),
        exclude_has_entry=False,
        message=(
            ".cairn/ does not appear ignored. Approve `git_exclude_cairn` to add it to "
            ".git/info/exclude (does not change shared .gitignore)."
        ),
        limitation=limitation,
    )


def ensure_git_exclude_cairn(workspace_root: Path, *, approve: bool) -> dict[str, Any]:
    """
    Append `.cairn/` to `.git/info/exclude` after explicit approval.

    Never stages or commits. Idempotent if entry already present.
    """
    if not approve:
        return {
            "ok": False,
            "error": "approval_required",
            "message": "Set approve=true to write .git/info/exclude.",
        }
    repo = git_toplevel(workspace_root)
    if repo is None:
        return {
            "ok": False,
            "error": "not_a_git_repo",
            "message": "Workspace is not inside a git work tree.",
        }
    exclude = exclude_file(repo)
    info = exclude.parent
    try:
        info.mkdir(parents=True, exist_ok=True)
        existing = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    except OSError as exc:
        return {"ok": False, "error": "exclude_unwritable", "message": str(exc)}
    if exclude_has_cairn(repo) or any(
        line.strip() in {".cairn/", ".cairn"} for line in existing.splitlines()
    ):
        return {
            "ok": True,
            "changed": False,
            "path": str(exclude),
            "message": ".cairn/ already present in exclude.",
        }
    block = existing
    if block and not block.endswith("\n"):
        block += "\n"
    block += f"\n{EXCLUDE_MARKER}\n{EXCLUDE_ENTRY}\n"
    try:
        exclude.write_text(block, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "error": "exclude_unwritable", "message": str(exc)}
    return {
        "ok": True,
        "changed": True,
        "path": str(exclude),
        "message": "Added .cairn/ to .git/info/exclude (local only; not shared .gitignore).",
    }


def export_path_warnings(workspace_root: Path, export_path: Path) -> list[str]:
    """Warn when an export lands on a tracked path."""
    repo = git_toplevel(workspace_root)
    if repo is None:
        return []
    target = export_path.resolve()
    warnings: list[str] = []
    if path_is_tracked(repo, target) or path_is_tracked(repo, target.parent):
        warnings.append(
            f"Export path {target} is inside a git-tracked location. "
            "Prefer an untracked path under .cairn/exports/."
        )
    report = assess_git_privacy(workspace_root)
    if report.tracked_paths:
        warnings.append("Tracked Cairn data detected: " + ", ".join(report.tracked_paths[:5]))
    return warnings


def report_as_dict(report: GitPrivacyReport) -> dict[str, Any]:
    return {
        "kind": report.kind,
        "is_git_repo": report.is_git_repo,
        "cairn_ignored": report.cairn_ignored,
        "tracked_paths": report.tracked_paths,
        "exclude_path": report.exclude_path,
        "exclude_has_entry": report.exclude_has_entry,
        "message": report.message,
        "limitation": report.limitation,
    }
