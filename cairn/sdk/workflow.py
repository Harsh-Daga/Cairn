"""Workflow execution helpers."""

from __future__ import annotations

from pathlib import Path

from cairn.cache.store import CacheStore
from cairn.executor.runner import BuildOptions
from cairn.providers.registry import create_provider
from cairn.sdk.project import Project, Run
from cairn.workflow.engine import WorkflowEngine
from cairn.workflow.loader import load_workflow


def run(
    workflow_ref: str | None = None,
    *,
    project: str | Path = ".",
    context: str | None = None,
    provider_mode: str = "recorded",
    yes: bool = True,
    dry_run: bool = False,
) -> Run:
    """Execute a workflow and return a run handle for reporting."""
    opened = project if isinstance(project, Project) else Project.open(project)
    _ = context  # reserved for future context selector overrides
    loaded_project, workflow = load_workflow(opened.root, workflow_ref)
    engine = WorkflowEngine(loaded_project, workflow)
    cache = CacheStore(loaded_project.root)
    fixtures = Path(__file__).resolve().parents[1] / "data" / "fixtures"
    provider = create_provider(
        mode="recorded" if provider_mode == "recorded" else "live",
        fixtures_dir=fixtures,
        model=loaded_project.defaults_model,
    )
    try:
        if dry_run:
            result = engine.validate()
            if not result.ok:
                msg = f"workflow validation failed: {result.message}"
                raise ValueError(msg)
            return Run(
                project_root=opened.root,
                run_id="dry-run",
                kind="provider",
                workflow_ref=result.workflow_ref,
            )
        run_result = engine.run(
            cache,
            provider,
            options=BuildOptions(yes=yes, dry_run=False),
        )
    finally:
        cache.close()
    return Run(
        project_root=opened.root,
        run_id=run_result.run_id,
        kind="provider",
        workflow_ref=run_result.workflow_ref,
    )
