"""Load workflow definitions from cairn.toml projects."""

from __future__ import annotations

import re
from pathlib import Path

from cairn.loader.toml import load_project
from cairn.model.project import Project
from cairn.model.workflow import ContextSelector, WorkflowDef, WorkflowStep

_WORKFLOW_REF_RE = re.compile(r"^([a-zA-Z0-9_.-]+)(?:@(.+))?$")


def parse_workflow_ref(ref: str) -> tuple[str, str | None]:
    match = _WORKFLOW_REF_RE.match(ref.strip())
    if not match:
        msg = f"invalid workflow ref: {ref!r}"
        raise ValueError(msg)
    return match.group(1), match.group(2)


def load_workflow_from_project(
    project: Project,
    *,
    name: str = "default",
    version: str = "v1",
    description: str = "",
) -> WorkflowDef:
    includes: list[str] = []
    excludes: list[str] = []
    for source in project.sources.values():
        includes.extend(source.include)
        excludes.extend(source.exclude)
    steps = {
        step_name: WorkflowStep(
            name=step.name,
            kind=step.kind,
            prompt=step.prompt,
            output=step.output,
            model=step.model,
            params=dict(step.params),
            materialization=step.materialization,
            samples=step.samples,
            tags=step.tags,
            over=step.over,
            inputs=step.inputs,
            system=step.system,
        )
        for step_name, step in project.steps.items()
    }
    return WorkflowDef(
        name=name,
        version=version,
        description=description or f"{project.name} pipeline",
        status="validated",
        context=ContextSelector(
            include=tuple(includes),
            exclude=tuple(excludes),
        ),
        steps=steps,
        vars=dict(project.vars),
    )


def load_workflow(
    project_root: Path,
    workflow_ref: str | None = None,
) -> tuple[Project, WorkflowDef]:
    project = load_project(project_root)
    if workflow_ref is None:
        return project, load_workflow_from_project(project)
    name, version = parse_workflow_ref(workflow_ref)
    ver = version or "v1"
    if name != "default":
        msg = f"only default workflow is supported from cairn.toml (got {name!r})"
        raise ValueError(msg)
    return project, load_workflow_from_project(project, name=name, version=ver)
