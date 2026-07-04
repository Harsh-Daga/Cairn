"""OpenClaw agent session parser.

Format inferred from community examples; verify against a real installation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.ingest.normalizer import args_payload, assign_seq, result_payload, text_payload
from cairn.ingest.parsers.claude_code import ToolCallDraft
from cairn.ingest.usage import UsageAccumulator, extract_usage_dict


@dataclass
class ParsedOpenClawSession:
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


def openclaw_root() -> Path:
    return Path.home() / ".openclaw"


def discover_openclaw_sessions(_repo_root: Path) -> list[Path]:
    root = openclaw_root()
    if not root.is_dir():
        return []
    paths: list[Path] = []
    for pattern in ("**/*.jsonl", "**/*.json"):
        for path in root.glob(pattern):
            if path.is_file() and _looks_like_openclaw(path):
                paths.append(path)
    return sorted(set(paths))


def _looks_like_openclaw(path: Path) -> bool:
    try:
        if path.suffix == ".jsonl":
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    obj = json.loads(stripped)
                    return isinstance(obj, dict) and ("event" in obj or "role" in obj)
        obj = json.loads(path.read_text(encoding="utf-8"))
        return isinstance(obj, dict) and ("events" in obj or "messages" in obj)
    except (OSError, json.JSONDecodeError):
        return False


def parse_openclaw_file(
    path: Path,
    *,
    repo_root: Path | None = None,
) -> ParsedOpenClawSession | None:
    del repo_root
    if path.suffix == ".jsonl":
        return _parse_jsonl(path)
    return _parse_json(path)


def _parse_jsonl(path: Path) -> ParsedOpenClawSession | None:
    external_id = path.stem
    session = ParsedOpenClawSession(
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
            if isinstance(obj, dict):
                _consume(session, obj, line_no=line_no)
    if not session.events:
        return None
    session.events = assign_seq(session.events)
    return session


def _parse_json(path: Path) -> ParsedOpenClawSession | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(obj, dict):
        return None
    external_id = str(obj.get("session_id") or path.stem)
    session = ParsedOpenClawSession(
        external_id=external_id,
        cwd=obj.get("cwd") if isinstance(obj.get("cwd"), str) else None,
        git_branch=None,
        started_at=None,
        ended_at=None,
        model=obj.get("model") if isinstance(obj.get("model"), str) else None,
    )
    events = obj.get("events") or obj.get("messages")
    if isinstance(events, list):
        for line_no, item in enumerate(events, start=1):
            if isinstance(item, dict):
                _consume(session, item, line_no=line_no)
    if not session.events:
        return None
    session.events = assign_seq(session.events)
    return session


def _consume(session: ParsedOpenClawSession, obj: dict[str, Any], *, line_no: int) -> None:
    ts = obj.get("timestamp") or obj.get("ts")
    if isinstance(ts, str):
        if session.started_at is None:
            session.started_at = ts
        session.ended_at = ts
    if isinstance(obj.get("cwd"), str):
        session.cwd = str(obj["cwd"])
    if isinstance(obj.get("model"), str):
        session.model = str(obj["model"])

    event_type = obj.get("event") or obj.get("type")
    role = obj.get("role")
    if event_type == "user_message" or role == "user":
        text = str(obj.get("content") or obj.get("text") or "")
        if text.strip():
            session.events.append(
                {"type": "user_prompt", **text_payload(text), "ts": ts, "line_no": line_no}
            )
        return
    if event_type in ("assistant_message", "assistant") or role == "assistant":
        text = str(obj.get("content") or obj.get("text") or "")
        usage_obj = obj.get("usage")
        usage_raw: dict[str, Any] = usage_obj if isinstance(usage_obj, dict) else {}
        usage = extract_usage_dict(usage_raw)
        session.usage.usage.add(usage)
        if text.strip():
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
        return
    if event_type == "tool_call":
        tool_use_id = str(obj.get("tool_use_id") or obj.get("id") or f"tool-{line_no}")
        name = str(obj.get("tool_name") or obj.get("name") or "tool")
        tool_input = obj.get("tool_input") or obj.get("input") or {}
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
        return
    if event_type == "tool_result":
        tool_use_id = str(obj.get("tool_use_id") or obj.get("id") or f"tool-{line_no}")
        text = str(obj.get("content") or obj.get("result") or "")
        session.events.append(
            {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "ts": ts,
                **result_payload(text),
                "line_no": line_no,
            }
        )
