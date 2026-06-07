"""ADR 0008: ledger contents must not influence action keys or plan classification."""

from __future__ import annotations

from pathlib import Path

from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.plan.action_key import action_key
from cairn.plan.planner import plan_build
from tests.test_invariants import _build
from tests.test_provider_config_invariant import _EmptyCache


def test_action_keys_unchanged_after_ledger_populated(
    project_dir: Path,
    fixtures_dir: Path,
) -> None:
    keys_before = _all_action_keys(project_dir)
    _build(project_dir, fixtures_dir)
    keys_after = _all_action_keys(project_dir)
    assert keys_before == keys_after


def test_plan_classification_unchanged_after_ledger_populated(
    project_dir: Path,
    fixtures_dir: Path,
) -> None:
    states_before = _plan_states(project_dir)
    _build(project_dir, fixtures_dir)
    states_after = _plan_states(project_dir)
    assert states_before == states_after


def _all_action_keys(project_dir: Path) -> tuple[str, ...]:
    project = load_project(project_dir)
    graph = build_graph(project)
    return tuple(action_key(p.node) for p in plan_build(project, graph, _EmptyCache()).nodes)


def _plan_states(project_dir: Path) -> tuple[tuple[str, str], ...]:
    project = load_project(project_dir)
    graph = build_graph(project)
    plan = plan_build(project, graph, _EmptyCache())
    return tuple((p.node.node_id, p.state) for p in plan.nodes)
