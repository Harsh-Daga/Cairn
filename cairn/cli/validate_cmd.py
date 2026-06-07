"""cairn validate — parse and validate without spending tokens."""

from __future__ import annotations

import argparse

from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.model.errors import CairnError


def run(args: argparse.Namespace) -> int:
    root = args.project.resolve()
    try:
        project = load_project(root)
        graph = build_graph(project)
    except CairnError as exc:
        print(f"validation failed: {exc}")
        return 1
    except Exception as exc:
        print(f"validation failed: {exc}")
        return 1
    print(f"OK: {project.name} v{project.version}")
    print(f"  sources: {len(project.sources)}")
    print(f"  steps: {len(project.steps)}")
    print(f"  nodes: {len(graph.nodes)}")
    return 0
