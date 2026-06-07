"""cairn graph — export capture session micro DAG."""

from __future__ import annotations

import argparse
import json
from typing import Any

from cairn.graph.session_graph import build_session_graph
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        print(f"session not found: {args.session_id}")
        return 1

    writer = CaptureWriter(root)
    try:
        summary = writer.load_session_by_external_id(args.session_id)
        if summary is None:
            print(f"session not found: {args.session_id}")
            return 1
        events = writer.load_events(summary.run_id)
        graph = build_session_graph(events)
    finally:
        writer.close()

    if args.format == "json":
        print(json.dumps(graph, indent=2, sort_keys=True))
        return 0

    print(_to_dot(graph))
    return 0


def _to_dot(graph: dict[str, Any]) -> str:
    lines = ["digraph session {"]
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id", ""))
            label = str(node.get("label", node_id)).replace('"', '\\"')
            lines.append(f'  "{node_id}" [label="{label}"];')
    if isinstance(edges, list):
        for edge in edges:
            if not isinstance(edge, dict):
                continue
            src = str(edge.get("from", ""))
            dst = str(edge.get("to", ""))
            kind = str(edge.get("kind", ""))
            lines.append(f'  "{src}" -> "{dst}" [label="{kind}"];')
    lines.append("}")
    return "\n".join(lines)
