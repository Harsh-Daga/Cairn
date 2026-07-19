"""Cursor agent-transcript JSONL normalization stage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.ingest.adapters.claude_code import FileArtifactDraft, ToolCallDraft
from server.ingest.adapters.cursor_models import (
    CURSOR_EDIT_TOOLS,
    USER_QUERY_RE,
    ParsedCursorSession,
    normalize_cursor_tool_name,
)
from server.ingest.normalizer import args_payload, text_payload
from server.ingest.project_paths import (
    cursor_subagent_external_id,
    path_rel_to_repo,
)


def parse_transcript_file(
    path: Path,
    *,
    repo_root: Path | None = None,
    external_id: str | None = None,
    parent_session_id: str | None = None,
) -> ParsedCursorSession | None:
    """Parse one Cursor ``agent-transcripts/.../*.jsonl`` file (legacy fallback).

    Transcripts carry no timestamps and no usage. We never store ``line:N``;
    ``started_at`` comes from the file mtime (ISO-8601) so the run is not
    pinned to 1 Jan 1970, and ``has_cost`` stays 0 with a data-note.
    """
    session_id = external_id or _session_id_from_path(path, parent_session_id)
    if session_id is None:
        return None
    state = _TranscriptState(
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
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat()
    except OSError:
        mtime = None
    return state.finish(mtime)


def _session_id_from_path(path: Path, parent_session_id: str | None) -> str | None:
    stem = path.stem
    if not stem:
        return None
    if parent_session_id is not None:
        return cursor_subagent_external_id(path, parent_session_id)
    parent_dir = path.parent.name
    if parent_dir == "subagents" and path.parent.parent.name:
        return cursor_subagent_external_id(path, path.parent.parent.name)
    return stem


def parse_transcript_tools(
    path: Path,
    *,
    repo_root: Path | None,
) -> tuple[
    list[dict[str, Any]], list[ToolCallDraft], list[FileArtifactDraft], list[dict[str, str]]
]:
    state = _TranscriptState(repo_root=repo_root, external_id=path.stem, parent_session_id=None)
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                state.consume(obj, line_no=line_no)
    return state._events, state._tool_calls, state._file_artifacts, state._sub_agent_links


class _TranscriptState:
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
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[ToolCallDraft] = []
        self._file_artifacts: list[FileArtifactDraft] = []
        self._sub_agent_links: list[dict[str, str]] = []
        self._seq_hint = 0
        self._tool_counter = 0

    def consume(self, obj: dict[str, Any], *, line_no: int) -> None:
        line_type = obj.get("type")
        if line_type == "turn_ended":
            self._parse_turn_ended(obj, line_no=line_no)
            return
        role = obj.get("role")
        if role == "user":
            self._parse_user(obj, line_no=line_no)
        elif role == "assistant":
            self._parse_assistant(obj, line_no=line_no)

    def finish(self, mtime: str | None) -> ParsedCursorSession:
        return ParsedCursorSession(
            external_id=self._external_id,
            cwd=self._cwd,
            git_branch=None,
            started_at=mtime,
            ended_at=mtime,
            model="cursor",
            parent_session_id=self._parent_session_id,
            events=self._events,
            tool_calls=self._tool_calls,
            file_artifacts=self._file_artifacts,
            sub_agent_links=self._sub_agent_links,
            has_cost=False,
            data_notes=["cursor: agent-transcript fallback has no token/cost data"],
        )

    def _next_seq_hint(self) -> int:
        self._seq_hint += 1
        return self._seq_hint

    def _next_tool_use_id(self, line_no: int, block_idx: int) -> str:
        self._tool_counter += 1
        return f"cursor:{line_no}:{block_idx}"

    def _parse_turn_ended(self, obj: dict[str, Any], *, line_no: int) -> None:
        status = obj.get("status")
        if status in (None, "success", "completed", "ok"):
            return
        error = obj.get("error")
        if isinstance(error, str) and error.strip():
            message = error.strip()
        elif isinstance(status, str) and status.strip():
            message = f"turn ended with status {status.strip()}"
        else:
            message = "turn ended with error"
        self._next_seq_hint()
        self._events.append(
            {
                "type": "error",
                "message": message,
                "fatal": False,
                "line_no": line_no,
            }
        )

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
        text = strip_user_query(text)
        if not text:
            return
        self._next_seq_hint()
        self._events.append({"type": "user_prompt", **text_payload(text)})

    def _parse_assistant(self, obj: dict[str, Any], *, line_no: int) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
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
            self._next_seq_hint()
            self._events.append(
                {"type": "assistant_message", "model": "cursor", **text_payload(text)}
            )
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
            {"type": "tool_call", "tool_use_id": tool_use_id, "name": norm_name, **payload}
        )
        path_rel = _extract_path_rel(name, tool_input, self._repo_root)
        if path_rel and norm_name == "edit":
            self._file_artifacts.append(
                FileArtifactDraft(
                    path_rel=path_rel, first_seq_hint=seq, last_seq_hint=seq, op="edit"
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


def strip_user_query(text: str) -> str:
    match = USER_QUERY_RE.search(text)
    if match:
        return match.group(1).strip()
    return text.strip()


def _extract_path_rel(
    tool_name: str,
    tool_input: dict[str, Any],
    repo_root: Path | None,
) -> str | None:
    if tool_name in CURSOR_EDIT_TOOLS or tool_name == "Delete":
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
