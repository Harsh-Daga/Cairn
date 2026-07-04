"""Unified diff for edited files in a session."""

from __future__ import annotations

import difflib
from pathlib import Path

from cairn.ingest.writer import CaptureWriter


def file_diff_for_session(root: Path, run_id: str, path_rel: str) -> str:
    writer = CaptureWriter(root)
    try:
        events = writer.load_events(run_id)
    finally:
        writer.close()

    before_lines: list[str] = []
    after_lines: list[str] = []
    target = root / path_rel
    if target.is_file():
        after_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()

    for event in events:
        if event.get("path_rel") != path_rel:
            continue
        if event.get("type") == "tool_result" and event.get("tool_norm_name") == "read":
            text = event.get("text_inline") or ""
            if text and not before_lines:
                before_lines = text.splitlines()
        if event.get("type") == "tool_result" and event.get("tool_norm_name") == "edit":
            text = event.get("text_inline") or ""
            if text:
                after_lines = text.splitlines()

    diff = list(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"a/{path_rel}",
            tofile=f"b/{path_rel}",
            lineterm="",
        )
    )
    if not diff:
        return f"--- no diff available for {path_rel}\n"
    return "\n".join(diff) + "\n"
