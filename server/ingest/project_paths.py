"""Project slug resolution and transcript discovery (R19.2)."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

_HERMES_PATH_RE = re.compile(r"(/[\w./-]+)")
_PROJECT_PATH_KEYS = frozenset(
    {
        "cwd",
        "directory",
        "project",
        "project_path",
        "projectPath",
        "repo",
        "repo_root",
        "repoRoot",
        "root_path",
        "rootPath",
        "workspace",
        "workspace_path",
        "workspacePath",
    }
)
_ARTIFACT_PATH_KEYS = frozenset(
    {"file", "file_path", "filePath", "filename", "path", "target", "target_file"}
)
_PROJECT_PROBE_BYTES = 1024 * 1024
_PROJECT_PROBE_DEPTH = 12


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
    if amount < 0:
        msg = f"invalid --since value: {value!r} (duration must be non-negative)"
        raise ValueError(msg)
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


def cursor_subagent_external_id(transcript_path: Path, parent_session_id: str) -> str:
    """Distinct external id for Cursor subagent transcripts (§12.5)."""
    return f"{parent_session_id}#subagent:{transcript_path.stem}"


def cursor_projects_root() -> Path:
    return Path.home() / ".cursor" / "projects"


def hermes_sessions_root() -> Path:
    return Path.home() / ".hermes" / "sessions"


def resolve_cursor_workspace(
    repo_root: Path,
    *,
    cursor_workspace: Path | None = None,
) -> Path | None:
    if cursor_workspace is not None and cursor_workspace.is_dir():
        return cursor_workspace.resolve()
    for slug in cursor_workspace_slugs(repo_root):
        candidate = cursor_projects_root() / slug
        if candidate.is_dir():
            return candidate.resolve()
    return None


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


def read_codex_session_cwd(path: Path) -> str | None:
    """Read ``cwd`` from the first ``session_meta`` line in a Codex rollout."""
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                obj = json.loads(stripped)
                if obj.get("type") != "session_meta":
                    continue
                payload = obj.get("payload")
                if isinstance(payload, dict):
                    cwd = payload.get("cwd")
                    return str(cwd) if isinstance(cwd, str) else None
                break
    except (OSError, json.JSONDecodeError):
        return None
    return None


def cursor_composer_matches_project(
    project_root: Path,
    composer_cwd: str | None,
    *,
    composer_id: str | None = None,
    project_composer_ids: set[str] | None = None,
) -> bool:
    """True when a Cursor composer belongs to ``project_root``.

    Matches ``source`` workspace path when present, otherwise composer ids that
    have agent-transcripts under this repo's Cursor workspace.
    """
    if composer_cwd and _path_under_project(composer_cwd, project_root):
        return True
    return bool(composer_id and project_composer_ids and composer_id in project_composer_ids)


def codex_cwd_matches_project(project_root: Path, session_cwd: str) -> bool:
    """True when Codex session cwd is under ``project_root`` (§11.3)."""
    project = project_root.resolve()
    session = Path(session_cwd).resolve()
    try:
        session.relative_to(project)
        return True
    except ValueError:
        return session == project


def discover_codex_rollouts(
    repo_root: Path,
    *,
    since: datetime | None = None,
) -> list[Path]:
    """Glob Codex ``rollout-*.jsonl`` files whose session cwd matches the project."""
    root = codex_sessions_root()
    if not root.is_dir():
        return []
    project = repo_root.resolve()
    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in sorted(root.rglob("rollout-*.jsonl")):
        resolved = path.resolve()
        if resolved in seen:
            continue
        cwd = read_codex_session_cwd(resolved)
        if cwd is None or not codex_cwd_matches_project(project, cwd):
            continue
        if since is not None and resolved.stat().st_mtime < since.timestamp():
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered


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


def discover_cursor_transcripts(
    repo_root: Path,
    *,
    cursor_workspace: Path | None = None,
    since: datetime | None = None,
) -> list[tuple[Path, str | None]]:
    """Discover Cursor parent and subagent transcript paths.

    Returns ``(path, parent_session_id)`` where parent id is ``None`` for parents.
    """
    base = resolve_cursor_workspace(repo_root, cursor_workspace=cursor_workspace)
    if base is None:
        return []
    transcripts_dir = base / "agent-transcripts"
    if not transcripts_dir.is_dir():
        return []

    ordered: list[tuple[Path, str | None]] = []
    seen: set[Path] = set()

    def add(path: Path, parent_id: str | None) -> None:
        resolved = path.resolve()
        if resolved in seen or not resolved.is_file():
            return
        if since is not None and resolved.stat().st_mtime < since.timestamp():
            return
        seen.add(resolved)
        ordered.append((resolved, parent_id))

    for session_dir in sorted(transcripts_dir.iterdir()):
        if not session_dir.is_dir():
            continue
        session_id = session_dir.name
        parent_path = session_dir / f"{session_id}.jsonl"
        if parent_path.is_file():
            add(parent_path, None)
        subagents = session_dir / "subagents"
        if subagents.is_dir():
            for sub_path in sorted(subagents.glob("*.jsonl")):
                add(sub_path, session_id)

    return ordered


def cursor_project_composer_ids(
    repo_root: Path,
    *,
    cursor_workspace: Path | None = None,
) -> set[str]:
    """Composer / subagent ids discovered under this repo's Cursor workspace."""
    ids: set[str] = set()
    for path, parent_id in discover_cursor_transcripts(
        repo_root, cursor_workspace=cursor_workspace
    ):
        if parent_id is None:
            ids.add(path.parent.name)
        else:
            ids.add(cursor_subagent_external_id(path, parent_id))
    return ids


def _path_under_project(path_str: str, project_root: Path) -> bool:
    try:
        Path(path_str).resolve().relative_to(project_root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _structured_value_matches_project(
    value: object,
    project_root: Path,
    *,
    key: str | None = None,
    depth: int = 0,
) -> bool:
    if depth > _PROJECT_PROBE_DEPTH:
        return False
    if isinstance(value, str):
        if key not in _PROJECT_PATH_KEYS | _ARTIFACT_PATH_KEYS:
            return False
        candidate = Path(value).expanduser()
        if not candidate.is_absolute():
            return False
        return _path_under_project(str(candidate), project_root)
    if isinstance(value, dict):
        return any(
            _structured_value_matches_project(
                child,
                project_root,
                key=str(child_key),
                depth=depth + 1,
            )
            for child_key, child in value.items()
        )
    if isinstance(value, list):
        return any(
            _structured_value_matches_project(
                child,
                project_root,
                key=key,
                depth=depth + 1,
            )
            for child in value
        )
    return False


def structured_log_matches_project(path: Path, project_root: Path) -> bool:
    """Conservatively accept a global log only with explicit in-project path evidence."""
    try:
        with path.open("rb") as handle:
            raw = handle.read(_PROJECT_PROBE_BYTES + 1)
    except OSError:
        return False
    if len(raw) > _PROJECT_PROBE_BYTES:
        return False
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False
    try:
        if path.suffix == ".jsonl":
            values: list[object] = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            values = [json.loads(text)]
    except json.JSONDecodeError:
        return False
    return any(_structured_value_matches_project(value, project_root) for value in values)


def _hermes_message_paths(message: dict[str, object]) -> list[str]:
    paths: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        paths.extend(_HERMES_PATH_RE.findall(content))
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            fn = call.get("function")
            if not isinstance(fn, dict):
                continue
            raw_args = fn.get("arguments")
            if isinstance(raw_args, str):
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError:
                    paths.extend(_HERMES_PATH_RE.findall(raw_args))
                else:
                    if isinstance(args, dict):
                        for key in ("path", "file_path", "file", "target", "directory"):
                            val = args.get(key)
                            if isinstance(val, str) and val.startswith("/"):
                                paths.append(val)
                        command = args.get("command")
                        if isinstance(command, str):
                            paths.extend(_HERMES_PATH_RE.findall(command))
    return paths


def hermes_session_matches_project(path: Path, project_root: Path) -> bool:
    """True when a Hermes session references paths under ``project_root`` (§12.5.1)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(data, dict):
        return False
    project_posix = project_root.resolve().as_posix()
    messages = data.get("messages")
    if not isinstance(messages, list):
        return False
    for message in messages:
        if not isinstance(message, dict):
            continue
        for path_str in _hermes_message_paths(message):
            if _path_under_project(path_str, project_root):
                return True
        content = message.get("content")
        if isinstance(content, str) and project_posix in content:
            return True
    return False


def discover_hermes_sessions(
    repo_root: Path,
    *,
    since: datetime | None = None,
) -> list[Path]:
    """Glob Hermes ``session_*.json`` files that match the project (§11.5.1)."""
    root = hermes_sessions_root()
    if not root.is_dir():
        return []
    project = repo_root.resolve()
    ordered: list[Path] = []
    seen: set[Path] = set()
    for path in sorted(root.glob("session_*.json")):
        resolved = path.resolve()
        if resolved in seen:
            continue
        if not hermes_session_matches_project(resolved, project):
            continue
        if since is not None and resolved.stat().st_mtime < since.timestamp():
            continue
        seen.add(resolved)
        ordered.append(resolved)
    return ordered


def aider_sessions_root() -> Path:
    return Path.home() / ".aider" / "sessions"


def opencode_sessions_root() -> Path:
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "opencode" / "sessions"
    return Path.home() / ".local" / "share" / "opencode" / "sessions"


def goose_sessions_root() -> Path:
    return Path.home() / ".goose" / "sessions"


def discover_agent_jsonl_sessions(
    sessions_root: Path,
    *,
    project_root: Path | None = None,
    since: datetime | None = None,
) -> list[Path]:
    if not sessions_root.is_dir():
        return []
    paths: list[Path] = []
    for path in sorted(sessions_root.glob("**/*.jsonl")):
        if not path.is_file():
            continue
        if since is not None and path.stat().st_mtime < since.timestamp():
            continue
        if project_root is not None and not structured_log_matches_project(path, project_root):
            continue
        paths.append(path.resolve())
    return paths


def discover_aider_sessions(
    repo_root: Path,
    *,
    since: datetime | None = None,
) -> list[Path]:
    return discover_agent_jsonl_sessions(
        aider_sessions_root(),
        project_root=repo_root,
        since=since,
    )


def discover_opencode_sessions(
    repo_root: Path,
    *,
    since: datetime | None = None,
) -> list[Path]:
    return discover_agent_jsonl_sessions(
        opencode_sessions_root(),
        project_root=repo_root,
        since=since,
    )


def discover_goose_sessions(
    repo_root: Path,
    *,
    since: datetime | None = None,
) -> list[Path]:
    return discover_agent_jsonl_sessions(
        goose_sessions_root(),
        project_root=repo_root,
        since=since,
    )


def path_rel_to_repo(repo_root: Path, file_path: str) -> str | None:
    """Return repo-relative path if ``file_path`` is under ``repo_root``."""
    try:
        resolved = Path(file_path).resolve()
        return resolved.relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return None
