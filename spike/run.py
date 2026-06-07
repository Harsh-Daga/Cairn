"""CLI entry point for the Phase 0 spike."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from spike.cache import SpikeCache
from spike.dag import default_project
from spike.executor import build, nodes_that_would_run
from spike.provider import create_provider


def _print_report(report: object, *, verbose: bool) -> None:
    from spike.executor import BuildReport

    assert isinstance(report, BuildReport)
    print(f"\n{'NODE':<22} {'STATUS':<10} {'TOKENS':>8}")
    print("-" * 44)
    for node in report.results:
        status = "CACHED" if node.cache_hit else "RAN"
        tokens = node.input_tokens + node.output_tokens
        print(f"{node.node_id:<22} {status:<10} {tokens:>8}")
    print("-" * 44)
    print(
        f"Cache hits: {report.stats.hits}  "
        f"misses: {report.stats.misses}  "
        f"tokens spent: {report.stats.tokens_spent}"
    )
    if verbose:
        print("\nNodes executed (not cached):")
        for node_id in nodes_that_would_run(report):
            print(f"  - {node_id}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cairn Phase 0 spike — 3-node cached DAG")
    parser.add_argument("project", type=Path, help="Path to spike demo project root")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan only — compute keys and cache lookups without API calls",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use deterministic mock provider (offline, for tests)",
    )
    parser.add_argument(
        "--provider",
        choices=["ollama-cloud", "ollama", "openai", "mock"],
        default="ollama-cloud",
        help="Live provider backend (default: ollama-cloud)",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Show per-node detail")
    args = parser.parse_args(argv)

    project = default_project(args.project.resolve())
    cache = SpikeCache(project.root / ".cairn")
    provider_name = "mock" if args.mock else args.provider
    provider = create_provider(provider_name)

    mode = "dry-run" if args.dry_run else provider_name
    print(f"Building spike project at {project.root} [{mode}] model={project.model}")

    report = build(project, cache, provider, dry_run=args.dry_run)
    _print_report(report, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
