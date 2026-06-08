"""Phase 7 workflow engine tests."""

from __future__ import annotations

from pathlib import Path

from cairn.cache.store import CacheStore
from cairn.executor.runner import BuildOptions
from cairn.providers.recorded import RecordedProvider
from cairn.workflow.engine import WorkflowEngine, workflow_history
from cairn.workflow.loader import load_workflow, parse_workflow_ref


def test_parse_workflow_ref() -> None:
    assert parse_workflow_ref("default") == ("default", None)
    assert parse_workflow_ref("default@v1") == ("default", "v1")


def test_workflow_validate(project_dir: Path) -> None:
    project, workflow = load_workflow(project_dir)
    engine = WorkflowEngine(project, workflow)
    result = engine.validate()
    assert result.ok
    assert result.node_count > 0


def test_workflow_run_records_history(project_dir: Path, fixtures_dir: Path) -> None:
    project, workflow = load_workflow(project_dir)
    engine = WorkflowEngine(project, workflow)
    cache = CacheStore(project.root)
    provider = RecordedProvider(fixtures_dir)
    try:
        run_result = engine.run(
            cache,
            provider,
            options=BuildOptions(yes=True),
        )
        assert run_result.run_id
        assert run_result.workflow_ref == "default@v1"
        history = workflow_history(project.root, limit=5)
        assert any(r.run_id == run_result.run_id for r in history)
    finally:
        cache.close()


def test_workflow_cli_validate(project_dir: Path) -> None:
    from cairn.cli.workflow_cmd import run

    class Args:
        project = project_dir
        workflow_command = "validate"
        ref = None
        json = True
        dry_run = False
        yes = False
        max_cost = None
        provider_mode = "recorded"
        limit = 20

    assert run(Args()) == 0
