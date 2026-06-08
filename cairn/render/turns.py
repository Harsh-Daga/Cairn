"""Collapse capture events into navigable turns (§11.8.3, R19.12)."""

from __future__ import annotations

from typing import Any

_WRITE_TOOLS = frozenset({"edit", "write", "apply_patch", "multiedit", "delete"})
_TERMINAL_MARKERS = ("@", "%", "~ %")


def build_turns(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(events, key=lambda e: int(e.get("seq", 0)))
    turns: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for event in ordered:
        event_type = str(event.get("type", ""))
        seq = int(event.get("seq", 0))

        if event_type == "user_prompt":
            text = _inline_text(event, "text_inline")
            if _is_terminal_noise(text):
                if current is not None:
                    current["seq_end"] = seq
                continue
            if current is not None:
                turns.append(_finalize_turn(current, turn_id=len(turns) + 1))
            current = {
                "user": event,
                "assistant_parts": [],
                "tools": [],
                "seq_start": seq,
                "seq_end": seq,
            }
            continue

        if current is None:
            continue

        current["seq_end"] = seq
        if event_type == "assistant_message":
            current["assistant_parts"].append(event)
        elif event_type in ("tool_call", "tool_result", "file_snapshot", "sub_agent"):
            current["tools"].append(event)

    if current is not None:
        turns.append(_finalize_turn(current, turn_id=len(turns) + 1))

    return turns


def _finalize_turn(state: dict[str, Any], *, turn_id: int) -> dict[str, Any]:
    user = state["user"]
    assistant_parts: list[dict[str, Any]] = state["assistant_parts"]
    tools: list[dict[str, Any]] = state["tools"]

    assistant_summary = _assistant_summary(assistant_parts)
    tool_calls = [t for t in tools if t.get("type") == "tool_call"]
    files_touched = _files_touched(tools)

    return {
        "turn_id": turn_id,
        "seq_start": state["seq_start"],
        "seq_end": state["seq_end"],
        "user_text": _inline_text(user, "text_inline"),
        "user_seq": int(user.get("seq", state["seq_start"])),
        "assistant_summary": assistant_summary,
        "tool_count": len(tool_calls),
        "files_touched": files_touched,
        "events": [user, *assistant_parts, *tools],
    }


def _assistant_summary(parts: list[dict[str, Any]]) -> str:
    chunks: list[str] = []
    for part in parts:
        text = _inline_text(part, "text_inline")
        if text:
            chunks.append(text)
    merged = "\n\n".join(chunks).strip()
    if not merged:
        return ""
    first_para = merged.split("\n\n", maxsplit=1)[0].strip()
    if len(first_para) > 200:
        return first_para[:197] + "…"
    return first_para


def _inline_text(event: dict[str, Any], key: str) -> str:
    val = event.get(key)
    return val.strip() if isinstance(val, str) else ""


def _is_terminal_noise(text: str) -> bool:
    """Cursor/Codex often inject shell prompts as synthetic user_prompt lines."""
    if not text:
        return True
    if text.strip().startswith("[CONTEXT COMPACTION"):
        return True
    first_line = text.strip().split("\n", maxsplit=1)[0]
    collapsed = " ".join(first_line.split())
    if len(collapsed) > 200:
        return False
    has_shell = any(marker in collapsed for marker in _TERMINAL_MARKERS)
    return has_shell and len(collapsed.split()) <= 20


def _files_touched(tools: list[dict[str, Any]]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    for event in tools:
        if event.get("type") == "file_snapshot":
            path_rel = event.get("path_rel")
            if isinstance(path_rel, str) and path_rel not in seen:
                seen.add(path_rel)
                paths.append(path_rel)
            continue
        if event.get("type") != "tool_call":
            continue
        name = str(event.get("name", "")).lower()
        if name not in _WRITE_TOOLS and name != "read":
            continue
        path_rel = _path_from_tool(event)
        if path_rel and path_rel not in seen:
            seen.add(path_rel)
            paths.append(path_rel)
    return paths


def _path_from_tool(event: dict[str, Any]) -> str | None:
    args = event.get("args_inline")
    if not isinstance(args, dict):
        return None
    for key in ("path", "file_path", "target_file"):
        val = args.get(key)
        if isinstance(val, str) and val:
            return val
    return None
