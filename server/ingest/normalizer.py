"""Source-specific parsed events → R7 v2 trajectory events."""

from __future__ import annotations

from typing import Any

from server.util.hash import canonical_json, hash_obj

INLINE_CAP = 64 * 1024

_SKIP_LINE_TYPES = frozenset(
    {
        "attachment",
        "permission-mode",
        "queue-operation",
        "last-prompt",
    }
)

_EDIT_TOOLS = frozenset({"Edit", "Write", "MultiEdit"})


def assign_seq(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Assign monotonic ``seq`` starting at 1 (R7)."""
    out: list[dict[str, Any]] = []
    for idx, event in enumerate(events, start=1):
        tagged = dict(event)
        tagged["seq"] = idx
        out.append(tagged)
    return out


def text_payload(text: str) -> dict[str, str]:
    """Hash + optional inline text under 64 KiB (R7, R17 #14)."""
    payload: dict[str, str] = {"text_hash": hash_obj(text)}
    encoded = text.encode("utf-8")
    if len(encoded) <= INLINE_CAP:
        payload["text_inline"] = text
    return payload


def args_payload(args: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {"args_hash": hash_obj(args)}
    encoded = canonical_json_bytes(args)
    if len(encoded) <= INLINE_CAP:
        payload["args_inline"] = args
    return payload


def result_payload(text: str) -> dict[str, str]:
    payload: dict[str, str] = {"result_hash": hash_obj(text)}
    encoded = text.encode("utf-8")
    if len(encoded) <= INLINE_CAP:
        payload["result_inline"] = text
    return payload


def canonical_json_bytes(obj: Any) -> bytes:
    return canonical_json(obj).encode("utf-8")


def extract_file_path(tool_name: str, tool_input: dict[str, Any]) -> str | None:
    if tool_name not in _EDIT_TOOLS:
        return None
    for key in ("file_path", "path"):
        val = tool_input.get(key)
        if isinstance(val, str) and val:
            return val
    return None
