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
_BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")
_KNOWN_SECRET_RE = re.compile(
    r"\b(?:sk-[A-Za-z0-9_-]{8,}|AKIA[0-9A-Z]{16}|"
    r"gh[opusr]_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,})\b"
)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|password|secret)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
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
        "first_user_request",
        "content",
        "code",
    }
)
_OPAQUE_REFERENCE_KEYS = frozenset(
    {
        "workspace_id",
        "trace_id",
        "span_id",
        "parent_span_id",
        "from_span_id",
        "to_span_id",
        "failure_origin_span_id",
        "cascade_root_span_id",
        "insight_id",
        "experiment_id",
        "event_id",
    }
)
_SAFE_OPAQUE_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def scrub_text(value: str, workspace_root: Path) -> str:
    """Remove paths, repository identifiers, URLs, git IDs, and code fragments."""
    text = _FENCED_CODE_RE.sub("[redacted code]", value)
    text = _CODE_LINE_RE.sub("[redacted code]", text)
    text = _INLINE_CODE_RE.sub("[redacted code]", text)
    text = _URL_RE.sub("<url>", text)
    text = _BEARER_RE.sub("Bearer <redacted>", text)
    text = _KNOWN_SECRET_RE.sub("<redacted credential>", text)
    text = _SECRET_ASSIGNMENT_RE.sub(r"\1\2<redacted>", text)
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
    if (
        key in _OPAQUE_REFERENCE_KEYS
        and isinstance(value, str)
        and _SAFE_OPAQUE_ID_RE.fullmatch(value)
        and _KNOWN_SECRET_RE.fullmatch(value) is None
    ):
        return value
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
