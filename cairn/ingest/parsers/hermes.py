"""Hermes session JSON parser (R19.11, §12.5.1)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.ingest.normalizer import args_payload, result_payload, text_payload
from cairn.ingest.parsers.claude_code import FileArtifactDraft, ToolCallDraft
from cairn.ingest.project_paths import path_rel_to_repo
from cairn.ingest.usage import UsageAccumulator

_COMPACTION_PREFIX = "[CONTEXT COMPACTION"
_PATH_IN_TEXT_RE = re.compile(r"(/[\w./-]+)")
_HERMES_EDIT = frozenset({"write_file", "patch", "apply_patch"})
_HERMES_READ = frozenset({"read_file", "list_dir"})
_HERMES_SEARCH = frozenset({"search_files", "grep", "find"})
_HERMES_BASH = frozenset({"terminal", "execute_code", "shell"})
_SKIP_TOOLS = frozenset({"skills_list", "todo", "plan"})


@dataclass
class ParsedHermesSession:
    external_id: str
    cwd: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)


def normalize_hermes_tool_name(name: str) -> str:
    if name in _HERMES_READ:
        return "read"
    if name in _HERMES_SEARCH:
        return "search"
    if name in _HERMES_EDIT:
        return "edit"
    if name in _HERMES_BASH:
        return "bash"
    if name.startswith("browser_"):
        return "read"
    return name.lower()


def parse_session_file(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> ParsedHermesSession | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    session_id = data.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        session_id = path.stem.removeprefix("session_")
    messages = data.get("messages")
    if not isinstance(messages, list) or not messages:
        return None

    state = _ParserState(
        path=path,
        repo_root=repo_root,
        external_id=session_id,
        model=data.get("model") if isinstance(data.get("model"), str) else None,
        started_at=data.get("session_start")
        if isinstance(data.get("session_start"), str)
        else None,
        ended_at=data.get("last_updated") if isinstance(data.get("last_updated"), str) else None,
    )
    for msg_idx, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        state.consume(message, msg_idx=msg_idx)
    return state.finish()


def infer_hermes_cwd(data: dict[str, Any], repo_root: Path) -> str | None:
    """Best-effort cwd from tool paths and terminal commands."""
    project = repo_root.resolve()
    hits: dict[str, int] = {}
    for message in data.get("messages", []):
        if not isinstance(message, dict):
            continue
        for path_str in _paths_from_message(message):
            if not _path_in_project(path_str, project):
                continue
            parent = _project_parent_for_path(path_str, project)
            if parent is not None:
                hits[parent] = hits.get(parent, 0) + 1
    if not hits:
        return str(project) if session_text_mentions_project(data, project) else None
    return max(hits, key=lambda k: hits[k])


def session_text_mentions_project(data: dict[str, Any], project_root: Path) -> bool:
    project = project_root.resolve().as_posix()
    for message in data.get("messages", []):
        if not isinstance(message, dict):
            continue
        for path_str in _paths_from_message(message):
            if _path_in_project(path_str, project_root):
                return True
        content = message.get("content")
        if isinstance(content, str) and project in content:
            return True
    return False


def _project_parent_for_path(path_str: str, project: Path) -> str | None:
    try:
        resolved = Path(path_str).resolve()
        if resolved == project:
            return str(project)
        resolved.relative_to(project)
        return str(project)
    except (OSError, ValueError):
        return None


def _path_in_project(path_str: str, project: Path) -> bool:
    try:
        Path(path_str).resolve().relative_to(project.resolve())
        return True
    except (OSError, ValueError):
        return False


def _paths_from_message(message: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    content = message.get("content")
    if isinstance(content, str):
        paths.extend(_PATH_IN_TEXT_RE.findall(content))
    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            paths.extend(_paths_from_tool_call(call))
    return paths


def _paths_from_tool_call(call: dict[str, Any]) -> list[str]:
    fn = call.get("function")
    if not isinstance(fn, dict):
        return []
    raw_args = fn.get("arguments")
    if not isinstance(raw_args, str):
        return []
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError:
        return _PATH_IN_TEXT_RE.findall(raw_args)
    if not isinstance(args, dict):
        return []
    paths: list[str] = []
    for key in ("path", "file_path", "file", "target", "directory"):
        val = args.get(key)
        if isinstance(val, str) and val.startswith("/"):
            paths.append(val)
    command = args.get("command")
    if isinstance(command, str):
        paths.extend(_PATH_IN_TEXT_RE.findall(command))
    return paths


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _extract_edit_path(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    if tool_name not in _HERMES_EDIT:
        return None
    for key in ("path", "file_path", "file", "target"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            return val
    return None


class _ParserState:
    def __init__(
        self,
        *,
        path: Path,
        repo_root: Path | None,
        external_id: str,
        model: str | None,
        started_at: str | None,
        ended_at: str | None,
    ) -> None:
        self._path = path
        self._repo_root = repo_root
        self._external_id = external_id
        self._model = model or "hermes"
        self._started_at = started_at
        self._ended_at = ended_at
        self._cwd: str | None = str(repo_root) if repo_root else None
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[ToolCallDraft] = []
        self._file_artifacts: list[FileArtifactDraft] = []
        self._usage = UsageAccumulator()
        self._seq_hint = 0
        self._tool_counter = 0

    def consume(self, message: dict[str, Any], *, msg_idx: int) -> None:
        role = message.get("role")
        if role == "user":
            self._parse_user(message, msg_idx=msg_idx)
        elif role == "assistant":
            self._parse_assistant(message, msg_idx=msg_idx)
        elif role == "tool":
            self._parse_tool(message, msg_idx=msg_idx)

    def finish(self) -> ParsedHermesSession:
        if self._repo_root is not None and self._cwd is None:
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._cwd = infer_hermes_cwd(data, self._repo_root)
            except (OSError, json.JSONDecodeError):
                pass
        return ParsedHermesSession(
            external_id=self._external_id,
            cwd=self._cwd,
            started_at=self._started_at,
            ended_at=self._ended_at,
            model=self._model,
            events=self._events,
            tool_calls=self._tool_calls,
            file_artifacts=self._file_artifacts,
            usage=self._usage,
        )

    def _next_seq_hint(self) -> int:
        self._seq_hint += 1
        return self._seq_hint

    def _next_tool_use_id(self, msg_idx: int, call_idx: int) -> str:
        self._tool_counter += 1
        return f"hermes:{msg_idx}:{call_idx}"

    def _parse_user(self, message: dict[str, Any], *, msg_idx: int) -> None:
        content = message.get("content")
        if not isinstance(content, str):
            return
        text = content.strip()
        if not text or text.startswith(_COMPACTION_PREFIX):
            return
        self._touch_timestamps(msg_idx)
        self._next_seq_hint()
        self._events.append(
            {
                "type": "user_prompt",
                **text_payload(text),
                "msg_idx": msg_idx,
            }
        )

    def _parse_assistant(self, message: dict[str, Any], *, msg_idx: int) -> None:
        model = message.get("model")
        if isinstance(model, str):
            self._model = model
        self._usage.absorb_message_usage(message)
        usage = message.get("usage")

        content = message.get("content")
        text = content.strip() if isinstance(content, str) else ""
        reasoning = message.get("reasoning")
        if isinstance(reasoning, str) and reasoning.strip():
            stripped = reasoning.strip()
            text = f"{stripped}\n\n{text}" if text else stripped

        if text:
            self._touch_timestamps(msg_idx)
            self._next_seq_hint()
            event: dict[str, Any] = {
                "type": "assistant_message",
                "model": self._model,
                **text_payload(text),
                "msg_idx": msg_idx,
            }
            if isinstance(usage, dict):
                event["usage"] = usage
            self._events.append(event)

        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            return
        for call_idx, call in enumerate(tool_calls):
            if isinstance(call, dict):
                self._emit_tool_call(call, msg_idx=msg_idx, call_idx=call_idx)

    def _parse_tool(self, message: dict[str, Any], *, msg_idx: int) -> None:
        tool_call_id = message.get("tool_call_id")
        if not isinstance(tool_call_id, str) or not tool_call_id:
            tool_call_id = self._next_tool_use_id(msg_idx, 0)
        content = message.get("content")
        text = content if isinstance(content, str) else json.dumps(content, default=str)
        self._touch_timestamps(msg_idx)
        self._next_seq_hint()
        self._events.append(
            {
                "type": "tool_result",
                "tool_use_id": tool_call_id,
                **result_payload(text),
                "msg_idx": msg_idx,
            }
        )

    def _emit_tool_call(
        self,
        call: dict[str, Any],
        *,
        msg_idx: int,
        call_idx: int,
    ) -> None:
        fn = call.get("function")
        if not isinstance(fn, dict):
            return
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            return
        if name in _SKIP_TOOLS:
            return
        tool_input = _parse_tool_arguments(fn.get("arguments"))
        tool_use_id = call.get("call_id") or call.get("id")
        if not isinstance(tool_use_id, str) or not tool_use_id:
            tool_use_id = self._next_tool_use_id(msg_idx, call_idx)
        norm_name = normalize_hermes_tool_name(name)
        seq = self._next_seq_hint()
        self._touch_timestamps(msg_idx)
        payload = args_payload(tool_input)
        self._events.append(
            {
                "type": "tool_call",
                "tool_use_id": tool_use_id,
                "name": norm_name,
                **payload,
                "msg_idx": msg_idx,
            }
        )
        self._tool_calls.append(
            ToolCallDraft(
                tool_use_id=tool_use_id,
                name=norm_name,
                args_hash=payload["args_hash"],
                seq_hint=seq,
            )
        )
        file_path = _extract_edit_path(name, tool_input)
        if file_path and self._repo_root is not None:
            path_rel = path_rel_to_repo(self._repo_root, file_path)
            if path_rel:
                self._file_artifacts.append(
                    FileArtifactDraft(
                        path_rel=path_rel,
                        first_seq_hint=seq,
                        last_seq_hint=seq,
                        op="edit",
                    )
                )
                self._tool_calls[-1].path_rel = path_rel

    def _touch_timestamps(self, msg_idx: int) -> None:
        marker = f"msg:{msg_idx}"
        if self._started_at is None:
            self._started_at = marker
        self._ended_at = marker
