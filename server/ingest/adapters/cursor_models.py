"""Shared Cursor parser models and tool normalization."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from server.ingest.adapters.claude_code import FileArtifactDraft, ToolCallDraft
from server.ingest.usage import UsageAccumulator

CURSOR_EDIT_TOOLS = frozenset({"Write", "StrReplace", "EditNotebook"})
CURSOR_READ_TOOLS = frozenset({"Read", "Glob", "Grep"})
USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)


@dataclass
class ParsedCursorSession:
    external_id: str
    cwd: str | None
    git_branch: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    parent_session_id: str | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    sub_agent_links: list[dict[str, str]] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    has_cost: bool = False
    is_best_of_n_subcomposer: bool = False
    num_sub_composers: int | None = None
    data_notes: list[str] = field(default_factory=list)


def normalize_cursor_tool_name(tool_name: str) -> str:
    if tool_name in CURSOR_READ_TOOLS:
        return "search" if tool_name == "Grep" else "read"
    if tool_name in CURSOR_EDIT_TOOLS:
        return "edit"
    if tool_name == "Shell":
        return "bash"
    if tool_name == "Delete":
        return "delete"
    if tool_name == "Task":
        return "sub_agent"
    return tool_name.lower()
