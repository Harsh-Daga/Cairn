"""Cursor agent-transcript parser (R19.7, §12.5)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.ingest.normalizer import args_payload, text_payload
from cairn.ingest.parsers.claude_code import FileArtifactDraft, ToolCallDraft
from cairn.ingest.project_paths import cursor_subagent_external_id, path_rel_to_repo
from cairn.ingest.usage import UsageAccumulator

_CURSOR_EDIT = frozenset({"Write", "StrReplace", "EditNotebook"})
_CURSOR_READ = frozenset({"Read", "Glob", "Grep"})
_USER_QUERY_RE = re.compile(r"<user_query>\s*(.*?)\s*</user_query>", re.DOTALL)


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


def normalize_cursor_tool_name(tool_name: str) -> str:
    if tool_name in _CURSOR_READ:
        return "search" if tool_name == "Grep" else "read"
    if tool_name in _CURSOR_EDIT:
        return "edit"
    if tool_name == "Shell":
        return "bash"
    if tool_name == "Delete":
        return "delete"
    if tool_name == "Task":
        return "sub_agent"
    return tool_name.lower()


def parse_transcript_file(
    path: Path,
    *,
    repo_root: Path | None = None,
    external_id: str | None = None,
    parent_session_id: str | None = None,
) -> ParsedCursorSession | None:
    """Parse one Cursor ``agent-transcripts/.../*.jsonl`` file."""
    session_id = external_id or _session_id_from_path(path, parent_session_id)
    if session_id is None:
        return None
    state = _ParserState(
        repo_root=repo_root,
        external_id=session_id,
        parent_session_id=parent_session_id,
    )
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            state.consume(obj, line_no=line_no)
    return state.finish()


def _session_id_from_path(path: Path, parent_session_id: str | None) -> str | None:
    stem = path.stem
    if not stem:
        return None
    if parent_session_id is not None:
        return cursor_subagent_external_id(path, parent_session_id)
    parent_dir = path.parent.name
    if parent_dir == "subagents" and path.parent.parent.name:
        return cursor_subagent_external_id(path, path.parent.parent.name)
    if path.name == f"{stem}.jsonl":
        return stem
    return stem


class _ParserState:
    def __init__(
        self,
        *,
        repo_root: Path | None,
        external_id: str,
        parent_session_id: str | None,
    ) -> None:
        self._repo_root = repo_root
        self._external_id = external_id
        self._parent_session_id = parent_session_id
        self._cwd: str | None = str(repo_root) if repo_root else None
        self._started_at: str | None = None
        self._ended_at: str | None = None
        self._model: str | None = "cursor"
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[ToolCallDraft] = []
        self._file_artifacts: list[FileArtifactDraft] = []
        self._sub_agent_links: list[dict[str, str]] = []
        self._usage = UsageAccumulator()
        self._seq_hint = 0
        self._tool_counter = 0

    def consume(self, obj: dict[str, Any], *, line_no: int) -> None:
        role = obj.get("role")
        if role == "user":
            self._parse_user(obj, line_no=line_no)
        elif role == "assistant":
            self._parse_assistant(obj, line_no=line_no)

    def finish(self) -> ParsedCursorSession:
        return ParsedCursorSession(
            external_id=self._external_id,
            cwd=self._cwd,
            git_branch=None,
            started_at=self._started_at,
            ended_at=self._ended_at,
            model=self._model,
            parent_session_id=self._parent_session_id,
            events=self._events,
            tool_calls=self._tool_calls,
            file_artifacts=self._file_artifacts,
            sub_agent_links=self._sub_agent_links,
            usage=self._usage,
        )

    def _next_seq_hint(self) -> int:
        self._seq_hint += 1
        return self._seq_hint

    def _next_tool_use_id(self, line_no: int, block_idx: int) -> str:
        self._tool_counter += 1
        return f"cursor:{line_no}:{block_idx}"

    def _parse_user(self, obj: dict[str, Any], *, line_no: int) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        if not isinstance(content, list):
            return
        text = _content_text(content)
        if not text:
            return
        text = _strip_user_query(text)
        if not text:
            return
        if self._started_at is None:
            self._started_at = f"line:{line_no}"
        self._ended_at = f"line:{line_no}"
        self._next_seq_hint()
        self._events.append(
            {
                "type": "user_prompt",
                **text_payload(text),
                "line_no": line_no,
            }
        )

    def _parse_assistant(self, obj: dict[str, Any], *, line_no: int) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
        model = message.get("model")
        if isinstance(model, str):
            self._model = model
        self._usage.absorb_message_usage(message)

        content = message.get("content")
        if not isinstance(content, list):
            return

        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(str(t) for t in text_parts if t).strip()
        if text:
            if self._started_at is None:
                self._started_at = f"line:{line_no}"
            self._ended_at = f"line:{line_no}"
            self._next_seq_hint()
            event: dict[str, Any] = {
                "type": "assistant_message",
                "model": self._model or "cursor",
                **text_payload(text),
                "line_no": line_no,
            }
            usage = message.get("usage")
            if isinstance(usage, dict):
                event["usage"] = usage
            self._events.append(event)

        block_idx = 0
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            self._emit_tool_call(block, line_no=line_no, block_idx=block_idx)
            block_idx += 1

    def _emit_tool_call(self, block: dict[str, Any], *, line_no: int, block_idx: int) -> None:
        name = block.get("name")
        tool_input = block.get("input")
        if not isinstance(name, str):
            return
        if not isinstance(tool_input, dict):
            tool_input = {}
        tool_use_id = block.get("id")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            tool_use_id = self._next_tool_use_id(line_no, block_idx)
        norm_name = normalize_cursor_tool_name(name)
        seq = self._next_seq_hint()
        payload = args_payload(tool_input)
        self._events.append(
            {
                "type": "tool_call",
                "tool_use_id": tool_use_id,
                "name": norm_name,
                **payload,
                "line_no": line_no,
            }
        )
        path_rel = _extract_path_rel(name, tool_input, self._repo_root)
        if path_rel and norm_name == "edit":
            self._file_artifacts.append(
                FileArtifactDraft(
                    path_rel=path_rel,
                    first_seq_hint=seq,
                    last_seq_hint=seq,
                    op="edit",
                )
            )
        if norm_name == "sub_agent":
            child_id = _subagent_child_id(tool_input)
            if child_id:
                self._sub_agent_links.append(
                    {
                        "parent_tool_use_id": tool_use_id,
                        "child_session_id": child_id,
                        "child_source": "cursor",
                    }
                )
        self._tool_calls.append(
            ToolCallDraft(
                tool_use_id=tool_use_id,
                name=norm_name,
                args_hash=str(payload["args_hash"]),
                seq_hint=seq,
                path_rel=path_rel,
            )
        )

    def _rel_path(self, file_path: str) -> str | None:
        if self._repo_root is None:
            return file_path
        return path_rel_to_repo(self._repo_root, file_path)


def _content_text(content: list[Any]) -> str:
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts).strip()


def _strip_user_query(text: str) -> str:
    match = _USER_QUERY_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_path_rel(
    tool_name: str,
    tool_input: dict[str, Any],
    repo_root: Path | None,
) -> str | None:
    if tool_name in _CURSOR_EDIT or tool_name == "Delete":
        for key in ("path", "file_path", "target_file"):
            val = tool_input.get(key)
            if isinstance(val, str) and val:
                if repo_root is None:
                    return val
                return path_rel_to_repo(repo_root, val)
    if tool_name == "Read":
        val = tool_input.get("path")
        if isinstance(val, str) and val:
            if repo_root is None:
                return val
            return path_rel_to_repo(repo_root, val)
    return None


def _subagent_child_id(tool_input: dict[str, Any]) -> str | None:
    for key in ("subagent_id", "agent_id", "session_id", "child_session_id"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            return val
    return None
