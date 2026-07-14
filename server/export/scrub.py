"""Shared privacy scrubbers for user-initiated local exports."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
_URL_RE = re.compile(r"(?:https?|git|ssh)://\S+")
_ABS_PATH_RE = re.compile(r"(?<!\w)(?:/[A-Za-z0-9._~+-]+){2,}")
_WINDOWS_PATH_RE = re.compile(r"\b[A-Za-z]:\\(?:[^\s\\]+\\)+[^\s\\]+")
_REL_PATH_RE = re.compile(r"\b(?:[A-Za-z0-9_.-]+/)+[A-Za-z0-9_.-]+\.[A-Za-z0-9]+\b")
_GIT_ID_RE = re.compile(r"\b[0-9a-fA-F]{12,40}\b")
_CODE_LINE_RE = re.compile(
    r"(?m)^\s*(?:from\s+\S+\s+import|import\s+\S+|def\s+\w+\s*\(|class\s+\w+|"
    r"function\s+\w+\s*\(|const\s+\w+\s*=|let\s+\w+\s*=|.*=>\s*[{(]).*$"
)
_SENSITIVE_KEYS = frozenset(
    {
        "cwd",
        "root_path",
        "path",
        "path_rel",
        "target_file",
        "project",
        "repository",
        "repo",
        "external_id",
        "git_branch",
        "git_commit",
        "title",
        "text_inline",
        "content",
        "code",
    }
)


def scrub_text(value: str, workspace_root: Path) -> str:
    """Remove paths, repository identifiers, URLs, git IDs, and code fragments."""
    text = _FENCED_CODE_RE.sub("[redacted code]", value)
    text = _CODE_LINE_RE.sub("[redacted code]", text)
    text = _INLINE_CODE_RE.sub("[redacted code]", text)
    text = _URL_RE.sub("<url>", text)
    root = workspace_root.resolve()
    for sensitive in (str(root), root.as_posix(), root.name, str(Path.home())):
        if sensitive:
            text = re.sub(re.escape(sensitive), "<redacted>", text, flags=re.IGNORECASE)
    text = _WINDOWS_PATH_RE.sub("<path>", text)
    text = _ABS_PATH_RE.sub("<path>", text)
    text = _REL_PATH_RE.sub("<path>", text)
    text = _GIT_ID_RE.sub("<identifier>", text)
    return " ".join(text.split())[:2000] or "[redacted]"


def scrub_export_value(value: Any, workspace_root: Path, *, key: str | None = None) -> Any:
    """Recursively scrub the existing generic export bundle."""
    if key in _SENSITIVE_KEYS:
        return "<redacted>"
    if isinstance(value, str):
        return scrub_text(value, workspace_root)
    if isinstance(value, list):
        return [scrub_export_value(item, workspace_root) for item in value]
    if isinstance(value, dict):
        return {
            str(child_key): scrub_export_value(child, workspace_root, key=str(child_key))
            for child_key, child in value.items()
        }
    return value
