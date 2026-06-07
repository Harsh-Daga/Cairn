"""cairn status — per-node state and cost estimate."""

from __future__ import annotations

import argparse

from cairn.cache.store import CacheStore
from cairn.executor.runner import _CachePlanView
from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.plan.planner import plan_build


def run(args: argparse.Namespace) -> int:
    project = load_project(args.project.resolve())
    graph = build_graph(project)
    cache = CacheStore(project.root)
    try:
        plan = plan_build(project, graph, _CachePlanView(cache))
    finally:
        cache.close()

    print(f"{'NODE':<24} {'STATE':<12} {'EST COST':>10}")
    print("-" * 50)
    for pn in plan.nodes:
        cost = "unpriced" if pn.cost_unpriced else f"${pn.estimated_cost or 0:.4f}"
        print(f"{pn.node.node_id:<24} {pn.state:<12} {cost:>10}")
    print("-" * 50)
    total = "unpriced" if plan.has_unpriced else f"${plan.total_estimated_cost:.4f}"
    print(f"Work nodes: {plan.work_count}  Estimated cost: {total}")
    return 0
