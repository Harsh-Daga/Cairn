"""cairn build — execute the work list."""

from __future__ import annotations

import argparse
from pathlib import Path

from cairn.cache.store import CacheStore
from cairn.executor.runner import BuildOptions, _CachePlanView, run_build_sync
from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.plan.planner import plan_build
from cairn.providers.registry import create_provider


def run(args: argparse.Namespace) -> int:
    project = load_project(args.project.resolve())
    graph = build_graph(project)
    cache = CacheStore(project.root)
    fixtures = Path(__file__).resolve().parents[1] / "data" / "fixtures"
    provider = create_provider(
        mode="recorded" if args.provider_mode == "recorded" else "live",
        fixtures_dir=fixtures,
        model=project.defaults_model,
    )

    try:
        plan = plan_build(project, graph, _CachePlanView(cache))
        if plan.work_count > 0 and not args.dry_run and not args.yes:
            total = (
                "unpriced"
                if plan.has_unpriced
                else f"${plan.total_estimated_cost:.4f}"
            )
            print(f"Plan: {plan.work_count} node(s) to run, estimated cost {total}")
            print("Re-run with --yes to confirm.")
            return 0

        refresh_keys: set[str] = set()
        for selector in args.refresh:
            for pn in plan.nodes:
                if selector in (pn.node.node_id, pn.node.step):
                    refresh_keys.add(pn.action_key)

        options = BuildOptions(
            dry_run=args.dry_run,
            refresh_keys=frozenset(refresh_keys),
            concurrency=args.concurrency,
            max_cost=args.max_cost,
            yes=args.yes,
        )

        result = run_build_sync(project, graph, cache, provider, options)
    finally:
        cache.close()

    if result.run_id:
        print(f"Run: {result.run_id}")

    print(f"\n{'NODE':<24} {'STATUS':<10} {'TOKENS':>8}")
    print("-" * 46)
    for node in result.nodes:
        status = "CACHED" if node.cache_hit else "RAN"
        tokens = node.input_tokens + node.output_tokens
        print(f"{node.node_id:<24} {status:<10} {tokens:>8}")
    print("-" * 46)
    print(
        f"hits={result.stats.hits} misses={result.stats.misses} "
        f"tokens={result.stats.tokens_spent}"
    )
    return 0
