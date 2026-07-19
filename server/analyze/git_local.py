"""Local read-only git helpers shared by outcomes and Guard."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

GIT_TIMEOUT_SECONDS = 5


def run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def is_git_repo(repo: Path) -> bool:
    result = run_git(repo, ["git", "rev-parse", "--is-inside-work-tree"])
    return bool(result and result.returncode == 0 and result.stdout.strip() == "true")


def parse_iso(timestamp: str) -> datetime | None:
    text = timestamp.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def git_log_shas(repo: Path, since: str, until: str) -> list[str]:
    args = ["git", "log", "--format=%H"]
    if since:
        args.append(f"--since={since}")
    if until:
        args.append(f"--until={until}")
    result = run_git(repo, args)
    if result is None or result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def files_for_commit(repo: Path, sha: str) -> list[str]:
    diff_result = run_git(repo, ["git", "diff", "--stat", "--name-only", f"{sha}^", sha])
    if diff_result is not None and diff_result.returncode == 0:
        return [line.strip() for line in diff_result.stdout.splitlines() if line.strip()]
    show_result = run_git(repo, ["git", "show", "--stat", "--name-only", "--format=", sha])
    if show_result is None:
        return []
    return [line.strip() for line in show_result.stdout.splitlines() if line.strip()]


def is_dirty(repo: Path) -> bool:
    result = run_git(repo, ["git", "status", "--porcelain"])
    return bool(result and result.returncode == 0 and result.stdout.strip())


def stash_count(repo: Path) -> int:
    result = run_git(repo, ["git", "stash", "list"])
    if result is None or result.returncode != 0:
        return 0
    return len([line for line in result.stdout.splitlines() if line.strip()])


def until_with_buffer(ended_at: str | None) -> str:
    if not ended_at:
        return ""
    parsed = parse_iso(ended_at)
    if parsed is None:
        return ended_at
    return (parsed + timedelta(hours=1)).isoformat()
