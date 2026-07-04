"""Claude Code JSONL parser (R19.3, §12.3)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.ingest.normalizer import (
    _EDIT_TOOLS,
    _SKIP_LINE_TYPES,
    args_payload,
    extract_file_path,
    result_payload,
    text_payload,
)
from server.ingest.project_paths import claude_subagent_external_id, path_rel_to_repo
from server.ingest.usage import UsageAccumulator, estimate_claude_turn

_SKIP_CONTENT_TYPES = frozenset({"attachment"})


@dataclass
class FileArtifactDraft:
    path_rel: str
    first_seq_hint: int
    last_seq_hint: int
    op: str = "edit"


@dataclass
class ToolCallDraft:
    tool_use_id: str
    name: str
    args_hash: str
    seq_hint: int
    path_rel: str | None = None


@dataclass
class ParsedClaudeSession:
    external_id: str
    cwd: str | None
    git_branch: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    parent_uuids: dict[str, str | None] = field(default_factory=dict)


def parse_jsonl_file(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> ParsedClaudeSession | None:
    """Parse one Claude Code ``*.jsonl`` transcript."""
    state = _ParserState(repo_root=repo_root, path=path)
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
    return state.finish(path)


class _ParserState:
    def __init__(self, *, repo_root: Path | None, path: Path | None = None) -> None:
        self._repo_root = repo_root
        self._path = path
        self._in_subagent = path is not None and "subagents" in path.parts
        self._external_id: str | None = None
        self._cwd: str | None = None
        self._git_branch: str | None = None
        self._started_at: str | None = None
        self._ended_at: str | None = None
        self._model: str | None = None
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[ToolCallDraft] = []
        self._file_artifacts: list[FileArtifactDraft] = []
        self._usage = UsageAccumulator()
        self._parent_uuids: dict[str, str | None] = {}
        self._seq_hint = 0
        self._seen_request_ids: set[str] = set()
        self._last_user_text: str = ""

    def _agent_fields(self, obj: dict[str, Any]) -> dict[str, str]:
        fields: dict[str, str] = {}
        agent_id = obj.get("agent_id")
        if isinstance(agent_id, str) and agent_id:
            fields["agent_id"] = agent_id
        elif self._external_id:
            fields["agent_id"] = self._external_id
        lane: str | None = None
        if obj.get("isSidechain") is True:
            lane = "sidechain"
        elif self._in_subagent:
            lane = "subagent"
        elif self._external_id and not self._in_subagent:
            lane = "main"
        if lane:
            fields["agent_lane"] = lane
        return fields

    def consume(self, obj: dict[str, Any], *, line_no: int) -> None:
        if self._external_id is None:
            sid = obj.get("sessionId")
            if isinstance(sid, str):
                self._external_id = sid
        if self._cwd is None:
            cwd = obj.get("cwd")
            if isinstance(cwd, str):
                self._cwd = cwd
        if self._git_branch is None:
            branch = obj.get("gitBranch")
            if isinstance(branch, str):
                self._git_branch = branch
        ts = obj.get("timestamp")
        if isinstance(ts, str):
            if self._started_at is None:
                self._started_at = ts
            self._ended_at = ts

        uuid = obj.get("uuid")
        if isinstance(uuid, str):
            parent = obj.get("parentUuid")
            self._parent_uuids[uuid] = parent if isinstance(parent, str) else None

        line_type = obj.get("type")
        if not isinstance(line_type, str):
            return
        if line_type in _SKIP_LINE_TYPES:
            return

        # Propagate the transcript timestamp into every emitted event so metrics
        # can do temporal attribution (by-hour, rollups, context curve).
        line_ts = obj.get("timestamp")
        line_ts_str = str(line_ts) if isinstance(line_ts, str) else None

        if line_type == "user":
            self._parse_user(obj, line_no=line_no, timestamp=line_ts_str)
        elif line_type == "assistant":
            self._parse_assistant(obj, line_no=line_no, timestamp=line_ts_str)
        elif line_type == "system":
            self._parse_system(obj, line_no=line_no, timestamp=line_ts_str)
        elif line_type == "file-history-snapshot":
            self._parse_file_snapshot(obj, line_no=line_no)

    def finish(self, path: Path | None = None) -> ParsedClaudeSession | None:
        if self._external_id is None:
            return None
        external_id = self._external_id
        if path is not None and "subagents" in path.parts:
            parent_id = path.parent.parent.name
            external_id = claude_subagent_external_id(path, parent_id)
        return ParsedClaudeSession(
            external_id=external_id,
            cwd=self._cwd,
            git_branch=self._git_branch,
            started_at=self._started_at,
            ended_at=self._ended_at,
            model=self._model,
            events=self._events,
            tool_calls=self._tool_calls,
            file_artifacts=self._file_artifacts,
            usage=self._usage,
            parent_uuids=self._parent_uuids,
        )

    def _next_seq_hint(self) -> int:
        self._seq_hint += 1
        return self._seq_hint

    def _parse_user(
        self, obj: dict[str, Any], *, line_no: int, timestamp: str | None = None
    ) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
        content = message.get("content")
        if not isinstance(content, list):
            return

        tool_results = [
            block
            for block in content
            if isinstance(block, dict) and block.get("type") == "tool_result"
        ]
        if tool_results:
            for block in tool_results:
                self._emit_tool_result(block, obj=obj, line_no=line_no, timestamp=timestamp)
            return

        text = _content_text(content)
        if text:
            self._last_user_text = text
            self._next_seq_hint()
            self._events.append(
                {
                    "type": "user_prompt",
                    **text_payload(text),
                    "timestamp": timestamp,
                    "line_no": line_no,
                    **self._agent_fields(obj),
                }
            )

    def _parse_assistant(
        self, obj: dict[str, Any], *, line_no: int, timestamp: str | None = None
    ) -> None:
        message = obj.get("message")
        if not isinstance(message, dict):
            return
        model = message.get("model")
        if isinstance(model, str):
            self._model = model

        # requestId dedup (§2.1): streaming emits duplicate placeholder-usage
        # entries per requestId. Keep the last by skipping earlier duplicates'
        # usage absorption so cost math does not double-count.
        request_id = obj.get("requestId")
        if isinstance(request_id, str) and request_id:
            if request_id in self._seen_request_ids:
                return
            self._seen_request_ids.add(request_id)

        content = message.get("content")
        if not isinstance(content, list):
            return

        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") in ("text", "thinking")
        ]
        text = "\n".join(str(t) for t in text_parts if t).strip()
        visible_text = "\n".join(
            str(block.get("text", ""))
            for block in content
            if isinstance(block, dict) and block.get("type") == "text" and block.get("text")
        ).strip()

        raw_usage = message.get("usage")
        observed = estimate_claude_turn(
            raw_usage if isinstance(raw_usage, dict) else {},
            assistant_text=text,
            user_text=self._last_user_text,
            model=self._model,
        )
        self._usage.usage.add(observed)

        if visible_text:
            self._next_seq_hint()
            event: dict[str, Any] = {
                "type": "assistant_message",
                "model": self._model or "unknown",
                **text_payload(visible_text),
                "timestamp": timestamp,
                "line_no": line_no,
                "input_tokens": observed.input_tokens,
                "output_tokens": observed.output_tokens,
                "input_estimated": 1 if observed.input_estimated else 0,
                "output_estimated": 1 if observed.output_estimated else 0,
                **self._agent_fields(obj),
            }
            if observed.cache_read_tokens:
                event["cache_read_tokens"] = observed.cache_read_tokens
            if observed.cache_creation_tokens:
                event["cache_creation_tokens"] = observed.cache_creation_tokens
            self._events.append(event)
        self._last_user_text = ""

        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_use":
                continue
            self._emit_tool_call(block, obj=obj, line_no=line_no, timestamp=timestamp)

    def _parse_system(
        self, obj: dict[str, Any], *, line_no: int, timestamp: str | None = None
    ) -> None:
        subtype = obj.get("subtype")
        if subtype == "api_error":
            message = obj.get("message")
            text = message if isinstance(message, str) else json.dumps(obj)
            self._next_seq_hint()
            self._events.append(
                {
                    "type": "error",
                    "message": text,
                    "fatal": False,
                    "line_no": line_no,
                }
            )

    def _parse_file_snapshot(self, obj: dict[str, Any], *, line_no: int) -> None:
        snapshot = obj.get("snapshot")
        if not isinstance(snapshot, dict):
            return
        backups = snapshot.get("trackedFileBackups")
        if not isinstance(backups, dict):
            return
        for rel_path in backups:
            if not isinstance(rel_path, str):
                continue
            path_rel = self._rel_path(rel_path)
            if path_rel is None:
                continue
            seq = self._next_seq_hint()
            self._events.append(
                {
                    "type": "file_snapshot",
                    "path_rel": path_rel,
                    "op": "read",
                    "line_no": line_no,
                }
            )
            self._file_artifacts.append(
                FileArtifactDraft(
                    path_rel=path_rel,
                    first_seq_hint=seq,
                    last_seq_hint=seq,
                    op="read",
                )
            )

    def _emit_tool_call(
        self,
        block: dict[str, Any],
        *,
        obj: dict[str, Any],
        line_no: int,
        timestamp: str | None = None,
    ) -> None:
        tool_use_id = block.get("id")
        name = block.get("name")
        tool_input = block.get("input")
        if not isinstance(tool_use_id, str) or not isinstance(name, str):
            return
        if not isinstance(tool_input, dict):
            tool_input = {}
        seq = self._next_seq_hint()
        payload = args_payload(tool_input)
        self._events.append(
            {
                "type": "tool_call",
                "tool_use_id": tool_use_id,
                "name": name,
                "timestamp": timestamp,
                **payload,
                "line_no": line_no,
                **self._agent_fields(obj),
            }
        )
        path_rel: str | None = None
        if name in _EDIT_TOOLS:
            raw_path = extract_file_path(name, tool_input)
            if raw_path:
                path_rel = self._rel_path(raw_path)
                if path_rel:
                    self._file_artifacts.append(
                        FileArtifactDraft(
                            path_rel=path_rel,
                            first_seq_hint=seq,
                            last_seq_hint=seq,
                            op="edit",
                        )
                    )
        self._tool_calls.append(
            ToolCallDraft(
                tool_use_id=tool_use_id,
                name=name,
                args_hash=str(payload["args_hash"]),
                seq_hint=seq,
                path_rel=path_rel,
            )
        )

    def _emit_tool_result(
        self,
        block: dict[str, Any],
        *,
        obj: dict[str, Any],
        line_no: int,
        timestamp: str | None = None,
    ) -> None:
        tool_use_id = block.get("tool_use_id")
        if not isinstance(tool_use_id, str):
            return
        content = block.get("content")
        text = _tool_result_text(content)
        is_error = bool(block.get("is_error"))
        self._next_seq_hint()
        self._events.append(
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "timestamp": timestamp,
                **result_payload(text),
                "is_error": is_error,
                "line_no": line_no,
                **self._agent_fields(obj),
            }
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
        if block.get("type") in _SKIP_CONTENT_TYPES:
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str) and text:
                parts.append(text)
    return "\n".join(parts).strip()


def _tool_result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return _content_text(content)
    return json.dumps(content, sort_keys=True)
