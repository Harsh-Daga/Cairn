"""Assemble capture bundle v3 payload (R15 v2, R19.12)."""

from __future__ import annotations

import difflib
import re
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from cairn.cache.cas import ContentAddressableStore
from cairn.graph.engine import build_artifact_graph_from_files, build_execution_graph
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter, SessionSummary
from cairn.render.graph_layout import build_display_graph, layout_session_graph
from cairn.render.scrub import scrub_value
from cairn.render.turns import build_turns

DEFAULT_INLINE_CAP_BYTES = 64 * 1024
MAX_BUNDLE_EVENTS = 2000
_LINE_TIMESTAMP_RE = re.compile(r"^line:\d+$|^\d{4}-\d{2}-\d{2}T")


def assemble_capture_bundle(
    writer: CaptureWriter,
    session_id: str,
    cas: ContentAddressableStore,
    *,
    inline_cap: int = DEFAULT_INLINE_CAP_BYTES,
) -> dict[str, Any]:
    summary = writer.load_session_by_external_id(session_id)
    if summary is None:
        msg = f"session not found: {session_id}"
        raise FileNotFoundError(msg)

    events_raw = writer.load_events(summary.run_id)
    events_total = len(events_raw)
    events_body = events_raw
    events_truncated = False
    if events_total > MAX_BUNDLE_EVENTS:
        events_body = events_raw[:MAX_BUNDLE_EVENTS]
        events_truncated = True
    events = scrub_value(events_body)
    files = _enrich_files(
        writer.load_file_artifacts(summary.run_id),
        events,
        cas,
        inline_cap=inline_cap,
    )
    graph_events = events_raw if not events_truncated else events_body
    turns = build_turns(graph_events)
    execution_raw = build_execution_graph(graph_events)
    execution = {**layout_session_graph(execution_raw), "graph_kind": "execution"}
    artifact = build_artifact_graph_from_files(writer.load_file_artifacts(summary.run_id))
    graph = build_display_graph(events, turns, execution)
    blobs = _collect_blobs(events, cas, inline_cap=inline_cap)
    session = _session_header(summary)

    payload: dict[str, Any] = {
        "cairn_bundle_version": 3,
        "kind": "capture",
        "session": session,
        "turns": turns,
        "events": events,
        "events_total": events_total,
        "events_truncated": events_truncated,
        "files": files,
        "graph": graph,
        "graphs": {
            "execution": execution,
            "artifact": artifact,
        },
        "blobs": blobs,
    }
    return cast(dict[str, Any], scrub_value(payload))


def capture_bundle_from_project(
    project_root: Path,
    session_id: str,
    *,
    inline_cap: int = DEFAULT_INLINE_CAP_BYTES,
) -> dict[str, Any]:
    root = resolve_git_root(project_root) or project_root.resolve()
    writer = CaptureWriter(root)
    try:
        cas = ContentAddressableStore(root / ".cairn")
        return assemble_capture_bundle(
            writer,
            session_id,
            cas,
            inline_cap=inline_cap,
        )
    finally:
        writer.close()


def _session_header(summary: SessionSummary) -> dict[str, Any]:
    started = _display_timestamp(summary.started_at)
    ended = _display_timestamp(summary.ended_at) if summary.ended_at else None
    commit = summary.git_commit
    return {
        "run_id": summary.run_id,
        "external_id": summary.external_id,
        "id": summary.external_id,
        "session_key": f"{summary.source}:{summary.external_id}",
        "source": summary.source,
        "cwd": summary.cwd,
        "git": {
            "branch": summary.git_branch,
            "commit": commit,
            "commit_short": commit[:7] if isinstance(commit, str) and len(commit) >= 7 else commit,
        },
        "started_at": started,
        "ended_at": ended,
        "status": summary.status,
        "model": summary.model,
        "event_count": summary.event_count,
        "usage": {
            "input_tokens": summary.total_input_tokens,
            "output_tokens": summary.total_output_tokens,
            "cost": summary.total_cost,
        },
    }


def _display_timestamp(value: str | None) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    if _LINE_TIMESTAMP_RE.match(value):
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return value


def _enrich_files(
    files: list[dict[str, Any]],
    events: list[dict[str, Any]],
    cas: ContentAddressableStore,
    *,
    inline_cap: int,
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for file_row in files:
        row = dict(file_row)
        before = row.get("before_hash")
        after = row.get("after_hash")
        if isinstance(before, str) and isinstance(after, str) and before and after:
            row["snapshot_quality"] = "exact"
            row["diff_preview"] = _diff_preview(cas, before, after, inline_cap=inline_cap)
        elif before or after:
            row["snapshot_quality"] = "partial"
            row["diff_preview"] = None
        else:
            row["snapshot_quality"] = "inferred"
            row["diff_preview"] = _inferred_excerpt(row, events)
        row["change_type"] = _change_type(row, events)
        enriched.append(row)
    enriched.sort(key=lambda f: (-int(f.get("last_seq", 0)), str(f.get("path_rel", ""))))
    return enriched


def _change_type(file_row: dict[str, Any], events: list[dict[str, Any]]) -> str:
    path_rel = file_row.get("path_rel")
    if not isinstance(path_rel, str):
        return "edit"
    for event in events:
        if event.get("type") == "file_snapshot" and event.get("path_rel") == path_rel:
            return str(event.get("op", "edit"))
        if event.get("type") == "tool_call" and str(event.get("name", "")).lower() == "delete":
            args = event.get("args_inline")
            if isinstance(args, dict) and args.get("path") == path_rel:
                return "delete"
    return "edit"


def _diff_preview(
    cas: ContentAddressableStore,
    before_hash: str,
    after_hash: str,
    *,
    inline_cap: int,
) -> str | None:
    before_raw = cas.read(before_hash)
    after_raw = cas.read(after_hash)
    if before_raw is None or after_raw is None:
        return None
    before = before_raw.decode("utf-8", errors="replace").splitlines()
    after = after_raw.decode("utf-8", errors="replace").splitlines()
    diff = list(
        difflib.unified_diff(
            before,
            after,
            fromfile="before",
            tofile="after",
            lineterm="",
        )
    )
    if not diff:
        return "(no textual changes)"
    text = "\n".join(diff)
    if len(text.encode("utf-8")) > inline_cap:
        return text[: inline_cap // 2] + "\n… [diff truncated]"
    return text


def _inferred_excerpt(file_row: dict[str, Any], events: list[dict[str, Any]]) -> str | None:
    path_rel = file_row.get("path_rel")
    if not isinstance(path_rel, str):
        return None
    for event in events:
        if event.get("type") != "tool_call":
            continue
        args = event.get("args_inline")
        if not isinstance(args, dict):
            continue
        for key in ("path", "file_path", "target_file"):
            val = args.get(key)
            if isinstance(val, str) and path_rel in val:
                name = event.get("name", "tool")
                return f"{name} on {path_rel}"
    return None


def _collect_blobs(
    events: list[dict[str, Any]],
    cas: ContentAddressableStore,
    *,
    inline_cap: int,
) -> dict[str, str]:
    hashes: set[str] = set()
    for event in events:
        for key in (
            "text_hash",
            "args_hash",
            "result_hash",
            "before_hash",
            "after_hash",
        ):
            val = event.get(key)
            if isinstance(val, str) and val:
                hashes.add(val)
        for inline_key in ("text_inline", "result_inline"):
            if inline_key in event and isinstance(event.get(inline_key), str):
                continue

    blobs: dict[str, str] = {}
    for digest in sorted(hashes):
        raw = cas.read(digest)
        if raw is None:
            continue
        if len(raw) <= inline_cap:
            blobs[digest] = raw.decode("utf-8", errors="replace")
        else:
            head = raw[:inline_cap].decode("utf-8", errors="replace")
            blobs[digest] = head + "\n… [truncated]"
    return blobs
