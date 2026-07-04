"""Error-cascade detection."""

from __future__ import annotations

from typing import Any

from cairn.config import get_diagnose_setting


def detect_cascade(events: list[dict[str, Any]]) -> tuple[int | None, int, int]:
    """Return (cascade_root_seq, blast_events, blast_tokens)."""
    cascade_k = int(get_diagnose_setting("cascade_k"))
    waste_threshold = int(get_diagnose_setting("cascade_waste_threshold"))
    max_events = int(get_diagnose_setting("cascade_max_events"))
    lookahead = int(get_diagnose_setting("cascade_lookahead"))

    if len(events) > max_events:
        return None, 0, 0

    bad_roots: list[tuple[int, int, int]] = []
    for event in events:
        if event.get("type") != "tool_result":
            continue
        if not event.get("tool_is_error") and int(event.get("waste_tokens") or 0) < waste_threshold:
            continue
        root_seq = event.get("seq")
        if not isinstance(root_seq, int):
            continue
        path = event.get("path_rel")
        args_hash = event.get("args_hash")
        text = str(event.get("text_inline") or "")[:200]
        downstream = 0
        blast_tokens = 0

        for other in events:
            seq = other.get("seq")
            if not isinstance(seq, int):
                continue
            if seq <= root_seq:
                continue
            if seq > root_seq + lookahead:
                break
            linked = False
            if path and other.get("path_rel") == path:
                linked = True
            if args_hash and other.get("args_hash") == args_hash:
                linked = True
            if text and text in str(other.get("text_inline") or ""):
                linked = True
            if linked and (other.get("tool_is_error") or other.get("waste_category")):
                downstream += 1
                blast_tokens += int(other.get("waste_tokens") or 0) + int(
                    other.get("input_tokens") or 0
                )
        if downstream >= cascade_k:
            bad_roots.append((root_seq, downstream, blast_tokens))

    if not bad_roots:
        return None, 0, 0
    return max(bad_roots, key=lambda item: item[2])


__all__ = ["detect_cascade"]
