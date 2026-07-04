"""Error-cascade detection — Phase A."""

from __future__ import annotations

from typing import Any

from cairn.config import get_diagnose_setting


def detect_cascade(events: list[dict[str, Any]]) -> tuple[int | None, int, int]:
    """Return (cascade_root_event_id, blast_events, blast_tokens)."""
    cascade_k = int(get_diagnose_setting("cascade_k"))
    waste_threshold = int(get_diagnose_setting("cascade_waste_threshold"))
    max_events = int(get_diagnose_setting("cascade_max_events"))
    lookahead = int(get_diagnose_setting("cascade_lookahead"))

    if len(events) > max_events:
        # Honest skip — caller may attach a data-note (see diagnose/engine.py).
        return None, 0, 0

    id_by_seq = {int(e["seq"]): int(e["event_id"]) for e in events if e.get("event_id") is not None}
    bad_roots: list[tuple[int, int, int]] = []

    for e in events:
        if e.get("type") != "tool_result":
            continue
        if not e.get("tool_is_error") and int(e.get("waste_tokens") or 0) < waste_threshold:
            continue
        root_seq = int(e["seq"])
        root_id = id_by_seq.get(root_seq)
        if root_id is None:
            continue
        path = e.get("path_rel")
        args_hash = e.get("args_hash")
        text = str(e.get("text_inline") or "")[:200]
        downstream = 0
        blast_tokens = 0
        for other in events:
            oseq = int(other.get("seq") or 0)
            if oseq <= root_seq:
                continue
            if oseq > root_seq + lookahead:
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
            bad_roots.append((root_id, downstream, blast_tokens))

    if not bad_roots:
        return None, 0, 0
    best = max(bad_roots, key=lambda x: x[2])
    return best[0], best[1], best[2]
