"""Session replay — re-render capture bundle from ledger."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter
from cairn.render.html import render_capture_bundle


def replay_session(
    project_root: Path,
    session_id: str,
    *,
    output: Path | None = None,
) -> Path:
    """Re-render an ingested session to an offline provenance bundle."""
    root = resolve_git_root(project_root) or project_root.resolve()
    writer = CaptureWriter(root)
    try:
        summary = writer.load_session_by_external_id(session_id)
        if summary is None:
            msg = f"session not found: {session_id}"
            raise KeyError(msg)
    finally:
        writer.close()
    out = output or (root / "outputs" / "bundle")
    return render_capture_bundle(root, session_id, out)
