"""Assemble capture bundle v2 payload (R15 v2)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cairn.cache.cas import ContentAddressableStore
from cairn.graph.session_graph import build_session_graph
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter

DEFAULT_INLINE_CAP_BYTES = 64 * 1024


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

    events = writer.load_events(summary.run_id)
    files = writer.load_file_artifacts(summary.run_id)
    graph = build_session_graph(events)
    blobs = _collect_blobs(events, cas, inline_cap=inline_cap)

    return {
        "cairn_bundle_version": 2,
        "kind": "capture",
        "session": {
            "id": summary.external_id,
            "source": summary.source,
            "cwd": summary.cwd,
            "git": {
                "branch": summary.git_branch,
                "commit": summary.git_commit,
            },
            "started_at": summary.started_at,
            "ended_at": summary.ended_at,
            "status": summary.status,
            "model": summary.model,
            "usage": {
                "input_tokens": summary.total_input_tokens,
                "output_tokens": summary.total_output_tokens,
                "cost": summary.total_cost,
            },
        },
        "events": events,
        "files": files,
        "graph": graph,
        "blobs": blobs,
    }


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
