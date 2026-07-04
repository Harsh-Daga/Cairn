"""Codex rollout JSONL parser (R19.5, §12.4)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.ingest.normalizer import args_payload, result_payload, text_payload
from cairn.ingest.parsers.claude_code import FileArtifactDraft, ToolCallDraft
from cairn.ingest.project_paths import path_rel_to_repo
from cairn.ingest.usage import UsageAccumulator, extract_usage_dict
from cairn.ledger.resolve import hash_bytes

_PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$", re.MULTILINE)


@dataclass
class ParsedCodexSession:
    external_id: str
    cwd: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    file_artifacts: list[FileArtifactDraft] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    context_window: int | None = None
    rate_limit_used_pct: float | None = None
    rate_limit_window_min: int | None = None
    rate_limit_resets_at: str | None = None
    plan_type: str | None = None


def parse_rollout_file(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> ParsedCodexSession | None:
    state = _ParserState(path=path, repo_root=repo_root)
    if not _is_codex_rollout(path):
        return None
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


def _is_codex_rollout(path: Path) -> bool:
    """Only parse files whose first non-blank line is ``session_meta`` (§2.3)."""
    try:
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                obj = json.loads(stripped)
                return isinstance(obj, dict) and obj.get("type") == "session_meta"
    except (OSError, json.JSONDecodeError):
        return False
    return False


def extract_apply_patch_paths(patch: str) -> list[str]:
    return [m.group(1).strip() for m in _PATCH_PATH_RE.finditer(patch)]


def normalize_codex_tool_name(name: str) -> str:
    if name == "apply_patch":
        return "edit"
    if name in ("shell", "exec_command"):
        return "bash"
    if name in ("read_file", "list_dir"):
        return "read"
    if name.startswith("mcp__"):
        return f"mcp:{name[5:]}"
    return name


class _ParserState:
    def __init__(self, *, path: Path, repo_root: Path | None) -> None:
        self._path = path
        self._repo_root = repo_root
        self._external_id: str | None = None
        self._cwd: str | None = None
        self._started_at: str | None = None
        self._ended_at: str | None = None
        self._model: str | None = None
        self._events: list[dict[str, Any]] = []
        self._tool_calls: list[ToolCallDraft] = []
        self._file_artifacts: list[FileArtifactDraft] = []
        self._usage = UsageAccumulator()
        self._seq_hint = 0
        self._context_window: int | None = None
        self._rate_limit_used_pct: float | None = None
        self._rate_limit_window_min: int | None = None
        self._rate_limit_resets_at: str | None = None
        self._plan_type: str | None = None
        self._last_token_usage: dict[str, Any] | None = None

    def consume(self, obj: dict[str, Any], *, line_no: int) -> None:
        ts = obj.get("timestamp")
        if isinstance(ts, str):
            if self._started_at is None:
                self._started_at = ts
            self._ended_at = ts

        line_type = obj.get("type")
        if line_type == "session_meta":
            self._parse_session_meta(obj, line_no=line_no)
        elif line_type == "turn_context":
            self._parse_turn_context(obj)
        elif line_type == "event_msg":
            self._parse_event_msg(obj, line_no=line_no)
        elif line_type == "response_item":
            self._parse_response_item(obj, line_no=line_no)

    def finish(self) -> ParsedCodexSession | None:
        if self._external_id is None:
            return None
        return ParsedCodexSession(
            external_id=self._external_id,
            cwd=self._cwd,
            started_at=self._started_at,
            ended_at=self._ended_at,
            model=self._model,
            events=self._events,
            tool_calls=self._tool_calls,
            file_artifacts=self._file_artifacts,
            usage=self._usage,
            context_window=self._context_window,
            rate_limit_used_pct=self._rate_limit_used_pct,
            rate_limit_window_min=self._rate_limit_window_min,
            rate_limit_resets_at=self._rate_limit_resets_at,
            plan_type=self._plan_type,
        )

    def _next_seq_hint(self) -> int:
        self._seq_hint += 1
        return self._seq_hint

    def _parse_session_meta(self, obj: dict[str, Any], *, line_no: int) -> None:
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return
        sid = payload.get("id")
        if isinstance(sid, str):
            self._external_id = sid
        cwd = payload.get("cwd")
        if isinstance(cwd, str):
            self._cwd = cwd
        self._next_seq_hint()
        self._events.append(
            {
                "type": "session_start",
                "source": "codex",
                "cwd": self._cwd,
                "line_no": line_no,
            }
        )

    def _parse_turn_context(self, obj: dict[str, Any]) -> None:
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return
        model = payload.get("model")
        if isinstance(model, str):
            self._model = model

    def _parse_event_msg(self, obj: dict[str, Any], *, line_no: int) -> None:
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return
        msg_type = payload.get("type")
        if msg_type == "user_message":
            text = _user_message_text(payload)
            if text:
                self._next_seq_hint()
                self._events.append(
                    {
                        "type": "user_prompt",
                        **text_payload(text),
                        "line_no": line_no,
                    }
                )
        elif msg_type == "error":
            message = payload.get("message")
            text = message if isinstance(message, str) else json.dumps(payload)
            self._next_seq_hint()
            self._events.append(
                {
                    "type": "error",
                    "message": text,
                    "fatal": False,
                    "line_no": line_no,
                }
            )
        elif msg_type == "task_complete":
            usage = payload.get("usage")
            if isinstance(usage, dict):
                self._usage.usage.add(extract_usage_dict(usage))
        elif msg_type == "token_count":
            self._consume_token_count(payload, line_no=line_no)

    def _consume_token_count(self, payload: dict[str, Any], *, line_no: int) -> None:
        info = payload.get("info")
        if not isinstance(info, dict):
            return
        last = info.get("last_token_usage")
        if isinstance(last, dict):
            self._last_token_usage = last
            self._usage.usage.add(extract_usage_dict(last))
            total = _int(last, "total_tokens")
            if total:
                self._next_seq_hint()
                self._events.append(
                    {
                        "type": "token_count",
                        "line_no": line_no,
                        "context_tokens_after": total,
                        "input_tokens": _int(last, "input_tokens"),
                        "output_tokens": _int(last, "output_tokens"),
                        "cached_input_tokens": _int(last, "cached_input_tokens"),
                        "reasoning_output_tokens": _int(last, "reasoning_output_tokens"),
                    }
                )
        window = info.get("model_context_window")
        if isinstance(window, int) and window > 0:
            self._context_window = window
        rate_limits = payload.get("rate_limits")
        if isinstance(rate_limits, dict):
            primary = rate_limits.get("primary")
            if isinstance(primary, dict):
                used = primary.get("used_percent")
                if isinstance(used, (int, float)):
                    self._rate_limit_used_pct = float(used)
                window_min = primary.get("window_minutes")
                if isinstance(window_min, int):
                    self._rate_limit_window_min = window_min
                resets = primary.get("resets_at")
                if isinstance(resets, str):
                    self._rate_limit_resets_at = resets
            plan = rate_limits.get("plan_type")
            if isinstance(plan, str):
                self._plan_type = plan

    def _parse_response_item(self, obj: dict[str, Any], *, line_no: int) -> None:
        payload = obj.get("payload")
        if not isinstance(payload, dict):
            return
        item_type = payload.get("type")
        if item_type == "message":
            role = payload.get("role")
            if role != "assistant":
                return
            text = _message_content_text(payload.get("content"))
            if not text:
                return
            self._next_seq_hint()
            event: dict[str, Any] = {
                "type": "assistant_message",
                "model": self._model or "unknown",
                **text_payload(text),
                "line_no": line_no,
            }
            self._events.append(event)
        elif item_type == "function_call":
            self._emit_function_call(payload, line_no=line_no)
        elif item_type == "function_call_output":
            self._emit_function_output(payload, line_no=line_no)

    def _emit_function_call(self, payload: dict[str, Any], *, line_no: int) -> None:
        call_id = payload.get("call_id")
        name = payload.get("name")
        if not isinstance(call_id, str) or not isinstance(name, str):
            return
        args = _function_args(payload)
        seq = self._next_seq_hint()
        norm_name = normalize_codex_tool_name(name)
        arg_payload = args_payload(args)
        self._events.append(
            {
                "type": "tool_call",
                "tool_use_id": call_id,
                "name": norm_name,
                **arg_payload,
                "line_no": line_no,
            }
        )
        self._maybe_file_artifacts(norm_name, name, args, seq)
        self._tool_calls.append(
            ToolCallDraft(
                tool_use_id=call_id,
                name=norm_name,
                args_hash=str(arg_payload["args_hash"]),
                seq_hint=seq,
            )
        )

    def _emit_function_output(self, payload: dict[str, Any], *, line_no: int) -> None:
        call_id = payload.get("call_id")
        if not isinstance(call_id, str):
            return
        output = payload.get("output")
        text = output if isinstance(output, str) else json.dumps(output)
        is_error = bool(payload.get("is_error"))
        self._next_seq_hint()
        self._events.append(
            {
                "type": "tool_result",
                "tool_use_id": call_id,
                **result_payload(text),
                "is_error": is_error,
                "line_no": line_no,
            }
        )

    def _maybe_file_artifacts(
        self,
        norm_name: str,
        raw_name: str,
        args: dict[str, Any],
        seq: int,
    ) -> None:
        paths: list[str] = []
        if raw_name == "apply_patch":
            patch = args.get("patch") or args.get("input") or ""
            if isinstance(patch, str):
                paths = extract_apply_patch_paths(patch)
        elif norm_name == "read":
            for key in ("path", "file_path"):
                val = args.get(key)
                if isinstance(val, str):
                    paths = [val]
                    break
        for raw_path in paths:
            path_rel = self._rel_path(raw_path)
            if path_rel is None:
                continue
            before_hash = _file_hash_if_exists(raw_path, self._cwd)
            op = "edit" if norm_name == "edit" else "read"
            self._events.append(
                {
                    "type": "file_snapshot",
                    "path_rel": path_rel,
                    "op": op,
                    **({"before_hash": before_hash} if before_hash else {}),
                    "line_no": seq,
                }
            )
            self._file_artifacts.append(
                FileArtifactDraft(
                    path_rel=path_rel,
                    first_seq_hint=seq,
                    last_seq_hint=seq,
                    op=op,
                )
            )

    def _rel_path(self, file_path: str) -> str | None:
        base = self._repo_root
        if base is None and self._cwd:
            base = Path(self._cwd)
        if base is None:
            return file_path
        return path_rel_to_repo(base, file_path)


def _user_message_text(payload: dict[str, Any]) -> str:
    message = payload.get("message")
    if isinstance(message, str) and message:
        return message
    text_elements = payload.get("text_elements")
    if isinstance(text_elements, list):
        parts = [str(t) for t in text_elements if t]
        return "\n".join(parts).strip()
    return ""


def _message_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts).strip()
    return ""


def _function_args(payload: dict[str, Any]) -> dict[str, Any]:
    raw = payload.get("arguments") or payload.get("args") or payload.get("input")
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"raw": raw}
    return {}


def _file_hash_if_exists(file_path: str, cwd: str | None) -> str | None:
    path = Path(file_path)
    if not path.is_absolute() and cwd:
        path = Path(cwd) / path
    if not path.is_file():
        return None
    return hash_bytes(path.read_bytes())


def _int(obj: dict[str, Any], key: str) -> int:
    val = obj.get(key)
    if isinstance(val, bool):
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    return 0
