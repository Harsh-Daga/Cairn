"""Pillar 3 — git signal capture for a session's cwd (Part 11)."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

_GIT_TIMEOUT = 5


@dataclass
class GitSignals:
    commit_landed: bool
    commit_sha: str | None
    files_changed: list[str] = field(default_factory=list)
    uncommitted: bool = False
    dirty: bool = False
    stashes: int = 0
    data_notes: list[str] = field(default_factory=list)


def capture_git_signals(
    cwd: str | None,
    started_at: str | None,
    ended_at: str | None,
) -> GitSignals:
    """Inspect the session's repo for commits/files/uncommitted work."""
    if not cwd:
        return GitSignals(
            commit_landed=False,
            commit_sha=None,
            data_notes=["session has no cwd; git signals unknown"],
        )
    repo = Path(cwd)
    if not repo.is_dir():
        return GitSignals(
            commit_landed=False,
            commit_sha=None,
            data_notes=[f"cwd {cwd} is not a directory; git signals unknown"],
        )

    if not _is_git_repo(repo):
        return GitSignals(
            commit_landed=False,
            commit_sha=None,
            data_notes=[f"{cwd} is not a git repo; git signals unknown"],
        )

    notes: list[str] = []
    since = started_at or ""
    until = _until_with_buffer(ended_at)

    commits = _git_log(repo, since, until)
    commit_landed = bool(commits)
    commit_sha = commits[0] if commits else None
    files_changed: list[str] = []
    if commit_sha:
        files_changed = _files_for_commit(repo, commit_sha)

    dirty = _is_dirty(repo)
    stashes = _stash_count(repo)
    uncommitted = dirty or stashes > 0
    if not commit_landed and not uncommitted:
        notes.append("no commits and a clean tree: agent produced no landed or pending work")
    if uncommitted:
        notes.append("agent left uncommitted work (dirty tree or stashes)")

    return GitSignals(
        commit_landed=commit_landed,
        commit_sha=commit_sha,
        files_changed=files_changed,
        uncommitted=uncommitted,
        dirty=dirty,
        stashes=stashes,
        data_notes=notes,
    )


def _is_git_repo(repo: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        return r.returncode == 0 and r.stdout.strip() == "true"
    except (OSError, subprocess.TimeoutExpired):
        return False


def _git_log(repo: Path, since: str, until: str) -> list[str]:
    args = ["git", "log", "--format=%H"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    try:
        r = subprocess.run(
            args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if r.returncode != 0:
            return []
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _files_for_commit(repo: Path, sha: str) -> list[str]:
    try:
        r = subprocess.run(
            ["git", "diff", "--stat", "--name-only", f"{sha}^", sha],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if r.returncode != 0:
            # Root commit (no parent): fall back to show.
            r = subprocess.run(
                ["git", "show", "--stat", "--name-only", "--format=", sha],
                cwd=repo,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT,
                check=False,
            )
        return [line.strip() for line in r.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return []


def _is_dirty(repo: Path) -> bool:
    try:
        r = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        return r.returncode == 0 and bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def _stash_count(repo: Path) -> int:
    try:
        r = subprocess.run(
            ["git", "stash", "list"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if r.returncode != 0:
            return 0
        return len([line for line in r.stdout.splitlines() if line.strip()])
    except (OSError, subprocess.TimeoutExpired):
        return 0


def _until_with_buffer(ended_at: str | None) -> str:
    """Add a 1h buffer to the session end so a commit right after end counts."""
    if not ended_at:
        return ""
    parsed = _parse_iso(ended_at)
    if parsed is None:
        return ended_at
    return (parsed + timedelta(hours=1)).isoformat()


def _parse_iso(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def commit_before_timestamp(cwd: str | None, before_ts: str | None) -> str | None:
    """Last commit on the default branch strictly before *before_ts* (suggestion-only)."""
    if not cwd or not before_ts:
        return None
    repo = Path(cwd)
    if not _is_git_repo(repo):
        return None
    try:
        r = subprocess.run(
            ["git", "log", "-1", "--until", before_ts, "--format=%H"],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT,
            check=False,
        )
        if r.returncode != 0:
            return None
        sha = r.stdout.strip()
        return sha or None
    except (OSError, subprocess.TimeoutExpired):
        return None
