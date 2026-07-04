"""Mid-session loop guard — lightweight tail analysis for MCP."""

from __future__ import annotations

from typing import Any

from cairn.diagnose.cascade import detect_cascade
from cairn.diagnose.localize import localize_failure


def should_stop_verdict(events: list[dict[str, Any]], *, tail: int = 20) -> dict[str, Any]:
    """Structured verdict for cairn_should_i_stop (never false-positive on short sessions)."""
    if len(events) < 3:
        return {
            "should_stop": False,
            "reason": "insufficient signal",
            "suggestion": None,
        }

    window = events[-tail:] if len(events) > tail else events
    repeat = _max_identical_tool_streak(window)
    if repeat >= 3:
        tool = repeat_tool_name(window)
        return {
            "should_stop": True,
            "reason": f"same tool+args called {repeat}x with no new result",
            "suggestion": (
                f"Stop repeating {tool or 'that tool'} — re-read the file directly "
                "or change approach instead of grepping again"
            ),
        }

    origin_id, signature, _one_liner = localize_failure(window)
    _root, blast_events, _blast_tokens = detect_cascade(window)
    if origin_id is not None and signature and blast_events >= 2:
        return {
            "should_stop": True,
            "reason": f"failure pattern forming ({signature})",
            "suggestion": "Pause and verify the last tool result before continuing",
        }

    return {"should_stop": False, "reason": None, "suggestion": None}


def _max_identical_tool_streak(events: list[dict[str, Any]]) -> int:
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    best = 0
    streak = 0
    prev_key: tuple[str, str] | None = None
    for e in tool_calls:
        key = (
            str(e.get("tool_norm_name") or e.get("tool_name") or ""),
            str(e.get("args_hash") or ""),
        )
        if not key[0]:
            streak = 0
            prev_key = None
            continue
        if key == prev_key:
            streak += 1
        else:
            streak = 1
            prev_key = key
        best = max(best, streak)
    return best


def repeat_tool_name(events: list[dict[str, Any]]) -> str | None:
    for e in reversed(events):
        if e.get("type") == "tool_call":
            return str(e.get("tool_norm_name") or e.get("tool_name") or "")
    return None
