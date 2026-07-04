"""Cline / Roo Code / Kilo Code task-log parser (VS Code globalStorage shape)."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from server.ingest.adapters.claude_code import ToolCallDraft
from server.ingest.normalizer import args_payload, assign_seq, result_payload, text_payload
from server.ingest.usage import UsageAccumulator

_PUBLISHERS: dict[str, str] = {
    "saoudrizwan.claude-dev": "cline",
    "rooveterinaryinc.roo-cline": "roo",
    "kilocode.kilo-code": "kilo",
}


@dataclass
class ParsedClineSession:
    source: str
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


def cline_global_storage_roots() -> list[Path]:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return [home / "Library" / "Application Support" / "Code" / "User" / "globalStorage"]
    if system == "Linux":
        return [
            home / ".config" / "Code" / "User" / "globalStorage",
            home / ".vscode-server" / "data" / "User" / "globalStorage",
        ]
    return [home / "AppData" / "Roaming" / "Code" / "User" / "globalStorage"]


def discover_cline_sessions(_repo_root: Path) -> list[tuple[Path, str]]:
    found: list[tuple[Path, str]] = []
    for root in cline_global_storage_roots():
        if not root.is_dir():
            continue
        for publisher, source in _PUBLISHERS.items():
            tasks_root = root / publisher / "tasks"
            if not tasks_root.is_dir():
                continue
            for ui_path in tasks_root.glob("*/ui_messages.json"):
                if ui_path.is_file():
                    found.append((ui_path, source))
    return found


def parse_cline_task(
    ui_path: Path,
    *,
    source: str,
    repo_root: Path | None = None,
) -> ParsedClineSession | None:
    del repo_root
    try:
        messages = json.loads(ui_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(messages, list):
        return None

    task_id = ui_path.parent.name
    session = ParsedClineSession(
        source=source,
        external_id=f"{source}-{task_id}",
        cwd=None,
        git_branch=None,
        started_at=None,
        ended_at=None,
        model=None,
    )
    history_path = ui_path.parent / "api_conversation_history.json"
    if history_path.is_file():
        try:
            hist = json.loads(history_path.read_text(encoding="utf-8"))
            if isinstance(hist, dict):
                model = hist.get("model") or hist.get("apiModelId")
                if isinstance(model, str):
                    session.model = model
        except (OSError, json.JSONDecodeError):
            session.data_notes.append("api_conversation_history.json unreadable")

    for idx, msg in enumerate(messages, start=1):
        if not isinstance(msg, dict):
            continue
        ts = msg.get("ts") if isinstance(msg.get("ts"), str) else None
        if ts:
            if session.started_at is None:
                session.started_at = ts
            session.ended_at = ts
        say = msg.get("say")
        msg_type = msg.get("type")
        if say == "api_req_started" and msg_type == "say":
            _parse_api_req(session, msg, line_no=idx)
            continue
        if say in ("user_feedback", "text") or msg_type == "user":
            text = str(msg.get("text") or "")
            if text.strip():
                session.events.append(
                    {"type": "user_prompt", **text_payload(text), "ts": ts, "line_no": idx}
                )
            continue
        if say == "tool" or msg_type == "tool":
            name = str(msg.get("tool") or msg.get("toolName") or "tool")
            tool_use_id = str(msg.get("toolUseId") or msg.get("id") or f"tool-{idx}")
            tool_input = msg.get("toolInput") or msg.get("input") or {}
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
                    "line_no": idx,
                }
            )
            session.tool_calls.append(
                ToolCallDraft(tool_use_id, name, str(payload["args_hash"]), idx, None)
            )
            continue
        if say == "tool_result" or msg_type == "tool_result":
            tool_use_id = str(msg.get("toolUseId") or msg.get("id") or f"tool-{idx}")
            text = str(msg.get("text") or msg.get("content") or "")
            session.events.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "ts": ts,
                    **result_payload(text),
                    "line_no": idx,
                }
            )

    if not session.events:
        return None
    session.events = assign_seq(session.events)
    return session


def _parse_api_req(session: ParsedClineSession, msg: dict[str, Any], *, line_no: int) -> None:
    raw = msg.get("text")
    if not isinstance(raw, str) or not raw.strip():
        session.data_notes.append(f"api_req_started line {line_no}: missing usage text")
        return
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        session.data_notes.append(f"api_req_started line {line_no}: invalid JSON text")
        return
    if not isinstance(payload, dict):
        return
    model = payload.get("model") or payload.get("apiProtocol")
    if isinstance(model, str) and not session.model:
        session.model = model
    tokens_in = payload.get("tokensIn")
    tokens_out = payload.get("tokensOut")
    if isinstance(tokens_in, int) or isinstance(tokens_out, int):
        from server.ingest.usage import ObservedUsage

        usage = ObservedUsage(
            input_tokens=int(tokens_in or 0),
            output_tokens=int(tokens_out or 0),
        )
        session.usage.usage.add(usage)
        session.events.append(
            {
                "type": "assistant_message",
                "model": session.model,
                **text_payload("api request"),
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "line_no": line_no,
            }
        )
