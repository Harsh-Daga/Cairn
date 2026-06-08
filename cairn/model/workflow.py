"""Workflow definition and execution types (charter §5, Phase 3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from cairn.model.project import Materialization, StepKind

WorkflowStatus = Literal["draft", "validated", "archived"]


@dataclass(frozen=True)
class ContextSelector:
    """Selects project context assets for a workflow run."""

    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()

    def digest_input(self) -> dict[str, Any]:
        return {
            "include": list(self.include),
            "exclude": list(self.exclude),
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class WorkflowStep:
    """One step in a versioned workflow definition."""

    name: str
    kind: StepKind
    prompt: str
    output: str
    model: str | None
    params: dict[str, Any]
    materialization: Materialization
    samples: int
    tags: tuple[str, ...]
    over: str | None
    inputs: tuple[str, ...] | None
    system: str | None


@dataclass(frozen=True)
class WorkflowDef:
    """Versioned workflow: prompts + steps + context selection."""

    name: str
    version: str
    description: str
    status: WorkflowStatus
    context: ContextSelector
    steps: dict[str, WorkflowStep]
    vars: dict[str, Any] = field(default_factory=dict)

    @property
    def workflow_ref(self) -> str:
        return f"{self.name}@{self.version}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "workflow_ref": self.workflow_ref,
            "description": self.description,
            "status": self.status,
            "context": self.context.digest_input(),
            "steps": {
                name: {
                    "name": step.name,
                    "kind": step.kind,
                    "prompt": step.prompt,
                    "output": step.output,
                    "model": step.model,
                    "params": step.params,
                    "materialization": step.materialization,
                    "samples": step.samples,
                    "tags": list(step.tags),
                    "over": step.over,
                    "inputs": list(step.inputs) if step.inputs else None,
                    "system": step.system,
                }
                for name, step in self.steps.items()
            },
            "vars": self.vars,
        }


@dataclass(frozen=True)
class WorkflowRun:
    """Links an executed run to its workflow version and context digest."""

    run_id: str
    workflow_ref: str
    context_digest: str
    git_commit: str | None
