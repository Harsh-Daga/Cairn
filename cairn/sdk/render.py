"""Rendering helpers for the public SDK."""

from __future__ import annotations

from pathlib import Path

from cairn.render.html import render_bundle, render_capture_bundle
from cairn.sdk.project import Project, Run


def html(
    run: Run,
    *,
    output: Path | None = None,
) -> Path:
    """Render a self-contained HTML report for a run handle."""
    if run.kind == "capture":
        if run.session_id is None:
            msg = "capture run requires session_id"
            raise ValueError(msg)
        out = output or (run.project_root / "outputs" / "bundle")
        return render_capture_bundle(run.project_root, run.session_id, out)
    if run.run_id == "dry-run":
        msg = "cannot render a dry-run workflow"
        raise ValueError(msg)
    out = output or (run.project_root / "outputs" / "bundle")
    return render_bundle(run.project_root, out, run_id=run.run_id)


def report_json(
    run: Run,
    *,
    project: str | Path | None = None,
) -> dict[str, object]:
    """Return the unified observability report JSON for a run."""
    from cairn.report.engine import build_report

    root = run.project_root if project is None else Project.open(project).root
    if run.kind == "capture" and run.session_id:
        return build_report(root, session_id=run.session_id)
    return build_report(root, run_id=run.run_id)
