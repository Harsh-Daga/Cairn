"""Project slug resolution and transcript discovery (R19.2)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path


def claude_project_slug(repo_root: Path) -> str:
    """Absolute cwd with ``/`` → ``-`` (R19.2)."""
    return repo_root.resolve().as_posix().replace("/", "-")


def cursor_workspace_slugs(repo_root: Path) -> list[str]:
    p = repo_root.resolve().as_posix().strip("/")
    return [
        p.replace("/", "-"),
        "-" + p.replace("/", "-"),
    ]


def codex_sessions_root() -> Path:
    return Path.home() / ".codex" / "sessions"


def claude_projects_root() -> Path:
    return Path.home() / ".claude" / "projects"


def resolve_git_root(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).resolve()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def try_git_branch(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def try_git_commit(project_root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def parse_since(value: str) -> datetime:
    """Parse ``7d``, ``24h``, ``30m`` into a UTC cutoff datetime."""
    text = value.strip().lower()
    if not text:
        msg = "empty --since value"
        raise ValueError(msg)
    unit = text[-1]
    try:
        amount = int(text[:-1])
    except ValueError as exc:
        msg = f"invalid --since value: {value!r}"
        raise ValueError(msg) from exc
    now = datetime.now(UTC)
    if unit == "d":
        return now - timedelta(days=amount)
    if unit == "h":
        return now - timedelta(hours=amount)
    if unit == "m":
        return now - timedelta(minutes=amount)
    msg = f"invalid --since unit in {value!r} (use d, h, or m)"
    raise ValueError(msg)


def claude_subagent_external_id(transcript_path: Path, parent_session_id: str) -> str:
    """Distinct external id for sidechain subagent transcripts (§12.3)."""
    return f"{parent_session_id}#subagent:{transcript_path.stem}"


def _paths_from_sessions_index(base: Path) -> list[Path]:
    index_path = base / "sessions-index.json"
    if not index_path.is_file():
        return []
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    entries = data.get("entries")
    if not isinstance(entries, list):
        return []
    paths: list[Path] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        full_path = entry.get("fullPath")
        if isinstance(full_path, str):
            candidate = Path(full_path)
            if candidate.is_file():
                paths.append(candidate)
    return paths


def discover_claude_jsonl(
    repo_root: Path,
    *,
    claude_project_dir: Path | None = None,
    since: datetime | None = None,
) -> list[Path]:
    """Discover Claude Code JSONL transcripts for a project slug.

    Layouts supported (§12.3 + newer Claude Code storage):

    - ``<slug>/<session_uuid>.jsonl`` — primary (lattice-style)
    - ``<slug>/<session_uuid>/<session_uuid>.jsonl`` — nested parent
    - ``<slug>/<session_uuid>/subagents/*.jsonl`` — subagent sidechains
    - ``sessions-index.json`` ``fullPath`` entries when the file still exists
    """
    base = claude_project_dir or (claude_projects_root() / claude_project_slug(repo_root))
    if not base.is_dir():
        return []

    seen: set[Path] = set()
    ordered: list[Path] = []

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            return
        if since is not None and resolved.stat().st_mtime < since.timestamp():
            return
        seen.add(resolved)
        ordered.append(resolved)

    for path in _paths_from_sessions_index(base):
        add(path)
    for path in sorted(base.rglob("*.jsonl")):
        add(path)

    return ordered


def path_rel_to_repo(repo_root: Path, file_path: str) -> str | None:
    """Return repo-relative path if ``file_path`` is under ``repo_root``."""
    try:
        resolved = Path(file_path).resolve()
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None
