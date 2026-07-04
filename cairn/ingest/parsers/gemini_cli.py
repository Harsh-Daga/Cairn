"""Google Gemini CLI session log parser — defensive multi-root discovery."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.ingest.normalizer import args_payload, assign_seq, result_payload, text_payload
from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator, extract_usage_dict


@dataclass
class ParsedGeminiSession:
    external_id: str
    cwd: str | None
    git_branch: str | None
    started_at: str | None
    ended_at: str | None
    model: str | None
    events: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[ToolCallDraft] = field(default_factory=list)
    usage: UsageAccumulator = field(default_factory=UsageAccumulator)
    data_notes: list[str] = field(default_factory=list)


def gemini_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = []
    tmp_root = home / ".gemini" / "tmp"
    if tmp_root.is_dir():
        roots.append(tmp_root)
    for cfg in (home / ".config" / "gemini", home / ".config" / "google-gemini"):
        if cfg.is_dir():
            roots.append(cfg)
    return roots


def discover_gemini_sessions(_repo_root: Path) -> list[Path]:
    paths: list[Path] = []
    for root in gemini_roots():
        for pattern in ("**/*.jsonl", "**/*.json"):
            for path in root.glob(pattern):
                if path.is_file() and _looks_like_session(path):
                    paths.append(path)
    return sorted(set(paths))


def _looks_like_session(path: Path) -> bool:
    try:
        if path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    obj = json.loads(stripped)
                    return isinstance(obj, dict) and (
                        "role" in obj or "type" in obj or "messages" in obj
                    )
        if path.suffix == ".json":
            obj = json.loads(path.read_text(encoding="utf-8"))
            return isinstance(obj, dict) and ("messages" in obj or "session" in obj)
    except (OSError, json.JSONDecodeError):
        return False
    return False


def parse_gemini_file(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> ParsedGeminiSession | None:
    if path.suffix == ".jsonl":
        return _parse_jsonl(path, repo_root=repo_root)
    if path.suffix == ".json":
        return _parse_json(path, repo_root=repo_root)
    return None


def _parse_jsonl(path: Path, *, repo_root: Path | None) -> ParsedGeminiSession | None:
    del repo_root
    external_id = path.stem
    session = ParsedGeminiSession(
        external_id=external_id,
        cwd=None,
        git_branch=None,
        started_at=None,
        ended_at=None,
        model=None,
    )
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                session.data_notes.append(f"skipped malformed line {line_no}")
                continue
            if not isinstance(obj, dict):
                continue
            _consume_record(session, obj, line_no=line_no)
    if not session.events:
        return None
    session.events = assign_seq(session.events)
    return session


def _parse_json(path: Path, *, repo_root: Path | None) -> ParsedGeminiSession | None:
    del repo_root
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    external_id = str(obj.get("session_id") or obj.get("id") or path.stem)
    session = ParsedGeminiSession(
        external_id=external_id,
        cwd=obj.get("cwd") if isinstance(obj.get("cwd"), str) else None,
        git_branch=None,
        started_at=None,
        ended_at=None,
        model=obj.get("model") if isinstance(obj.get("model"), str) else None,
    )
    messages = obj.get("messages")
    if isinstance(messages, list):
        for line_no, msg in enumerate(messages, start=1):
            if isinstance(msg, dict):
                _consume_record(session, msg, line_no=line_no)
    else:
        _consume_record(session, obj, line_no=1)
    if not session.events:
        return None
    session.events = assign_seq(session.events)
    return session


def _consume_record(session: ParsedGeminiSession, obj: dict[str, Any], *, line_no: int) -> None:
    ts = obj.get("timestamp") or obj.get("ts")
    if isinstance(ts, str):
        if session.started_at is None:
            session.started_at = ts
        session.ended_at = ts
    model = obj.get("model")
    if isinstance(model, str):
        session.model = model
    cwd = obj.get("cwd")
    if isinstance(cwd, str):
        session.cwd = cwd

    role = obj.get("role")
    msg_type = obj.get("type")
    if role == "user" or msg_type == "user":
        text = _text_from_obj(obj)
        if text:
            session.events.append(
                {"type": "user_prompt", **text_payload(text), "ts": ts, "line_no": line_no}
            )
        return
    if role == "assistant" or msg_type == "assistant":
        text = _text_from_obj(obj)
        usage_obj = obj.get("usage")
        usage_raw: dict[str, Any] = usage_obj if isinstance(usage_obj, dict) else {}
        usage = extract_usage_dict(usage_raw)
        session.usage.usage.add(usage)
        if text:
            event: dict[str, Any] = {
                "type": "assistant_message",
                "model": session.model,
                **text_payload(text),
                "ts": ts,
                "line_no": line_no,
            }
            if usage.input_tokens:
                event["input_tokens"] = usage.input_tokens
            if usage.output_tokens:
                event["output_tokens"] = usage.output_tokens
            session.events.append(event)
        tools = obj.get("tool_calls") or obj.get("functionCalls")
        if isinstance(tools, list):
            for block in tools:
                if isinstance(block, dict):
                    _emit_tool(session, block, ts=ts, line_no=line_no)
        return
    if msg_type == "tool_call" or obj.get("tool_name"):
        _emit_tool(session, obj, ts=ts, line_no=line_no)
        return
    if msg_type == "tool_result" or role == "tool":
        tool_use_id = str(obj.get("tool_use_id") or obj.get("id") or f"tool-{line_no}")
        text = _text_from_obj(obj)
        session.events.append(
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "ts": ts,
                **result_payload(text),
                "line_no": line_no,
            }
        )


def _emit_tool(
    session: ParsedGeminiSession,
    obj: dict[str, Any],
    *,
    ts: str | None,
    line_no: int,
) -> None:
    tool_use_id = str(obj.get("id") or obj.get("tool_use_id") or f"tool-{line_no}")
    name = obj.get("name") or obj.get("tool_name")
    if not isinstance(name, str):
        name = "tool"
    tool_input = obj.get("input") or obj.get("args") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}
    payload = args_payload(tool_input)
    session.events.append(
        {
            "type": "tool_call",
            "tool_use_id": tool_use_id,
            "name": name,
            "ts": ts,
            **payload,
            "line_no": line_no,
        }
    )
    session.tool_calls.append(
        ToolCallDraft(tool_use_id, name, str(payload["args_hash"]), line_no, None)
    )


def _text_from_obj(obj: dict[str, Any]) -> str:
    for key in ("content", "text", "message"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
        if isinstance(val, list):
            parts = [str(x.get("text", "")) for x in val if isinstance(x, dict) and x.get("text")]
            joined = "\n".join(p for p in parts if p).strip()
            if joined:
                return joined
    return ""
