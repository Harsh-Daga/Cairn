"""cairn plan — execution order and rendered prompts."""

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

    for i, pn in enumerate(plan.nodes, 1):
        print(f"\n--- [{i}] {pn.node.node_id} ({pn.state}) ---")
        print(f"action_key: {pn.action_key[:16]}…")
        preview = pn.rendered_prompt[:200].replace("\n", " ")
        print(f"prompt: {preview}{'…' if len(pn.rendered_prompt) > 200 else ''}")
    return 0
