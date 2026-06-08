"""Validate, plan, and execute workflows via the build engine."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from cairn.cache.store import CacheStore
from cairn.context.registry import ContextRegistry
from cairn.executor.runner import BuildOptions, _CachePlanView, run_build_sync
from cairn.graph.builder import build_graph
from cairn.ledger.ledger import try_git_commit
from cairn.ledger.schema import migrate
from cairn.ledger.storage import link_prompt_ref, list_workflow_runs, record_workflow_run
from cairn.model.project import Project
from cairn.model.workflow import WorkflowDef, WorkflowRun
from cairn.plan.planner import Plan, plan_build
from cairn.providers.protocol import Provider
from cairn.util.canonical import hash_obj


@dataclass(frozen=True)
class ValidationResult:
    workflow_ref: str
    source_count: int
    step_count: int
    node_count: int
    ok: bool
    message: str


@dataclass(frozen=True)
class WorkflowRunResult:
    run_id: str
    workflow_ref: str
    context_digest: str
    node_count: int
    cache_hits: int


class WorkflowEngine:
    """Bridges WorkflowDef to the existing pipeline build executor."""

    def __init__(self, project: Project, workflow: WorkflowDef) -> None:
        self.project = project
        self.workflow = workflow

    def validate(self) -> ValidationResult:
        try:
            graph = build_graph(self.project)
        except Exception as exc:
            return ValidationResult(
                workflow_ref=self.workflow.workflow_ref,
                source_count=len(self.project.sources),
                step_count=len(self.workflow.steps),
                node_count=0,
                ok=False,
                message=str(exc),
            )
        return ValidationResult(
            workflow_ref=self.workflow.workflow_ref,
            source_count=len(self.project.sources),
            step_count=len(self.workflow.steps),
            node_count=len(graph.nodes),
            ok=True,
            message="OK",
        )

    def plan(self, cache: CacheStore) -> Plan:
        graph = build_graph(self.project)
        return plan_build(self.project, graph, _CachePlanView(cache))

    def context_digest(self) -> str:
        registry = ContextRegistry(self.project.root)
        try:
            assets = registry.list_assets()
            if not assets:
                assets = registry.scan()
            asset_hashes = sorted(a.content_hash for a in assets)
        finally:
            registry.close()
        payload = {
            "workflow": self.workflow.workflow_ref,
            "selector": self.workflow.context.digest_input(),
            "assets": asset_hashes,
        }
        return hash_obj(payload)

    def run(
        self,
        cache: CacheStore,
        provider: Provider,
        *,
        options: BuildOptions | None = None,
    ) -> WorkflowRunResult:
        validation = self.validate()
        if not validation.ok:
            msg = f"workflow validation failed: {validation.message}"
            raise ValueError(msg)
        graph = build_graph(self.project)
        build_options = options or BuildOptions(yes=True)
        result = run_build_sync(
            self.project,
            graph,
            cache,
            provider,
            build_options,
        )
        if result.run_id is None:
            msg = "workflow run did not produce a run_id"
            raise RuntimeError(msg)
        digest = self.context_digest()
        git_commit = try_git_commit(self.project.root)
        workflow_run = WorkflowRun(
            run_id=result.run_id,
            workflow_ref=self.workflow.workflow_ref,
            context_digest=digest,
            git_commit=git_commit,
        )
        self._persist_workflow_run(workflow_run)
        return WorkflowRunResult(
            run_id=result.run_id,
            workflow_ref=self.workflow.workflow_ref,
            context_digest=digest,
            node_count=len(result.nodes),
            cache_hits=result.stats.hits,
        )

    def _persist_workflow_run(self, workflow_run: WorkflowRun) -> None:
        db_path = self.project.root / ".cairn" / "ledger.db"
        conn = sqlite3.connect(db_path)
        try:
            migrate(conn)
            record_workflow_run(conn, workflow_run)
            for step in self.workflow.steps.values():
                prompt_name = Path(step.prompt).stem
                link_prompt_ref(
                    conn,
                    workflow_ref=self.workflow.workflow_ref,
                    prompt_name=prompt_name,
                    prompt_version="latest",
                )
        finally:
            conn.close()


def workflow_history(project_root: Path, *, limit: int = 20) -> list[WorkflowRun]:
    db_path = project_root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        return []
    conn = sqlite3.connect(db_path)
    try:
        migrate(conn)
        return list_workflow_runs(conn, limit=limit)
    finally:
        conn.close()
