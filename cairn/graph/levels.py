"""Dependency levels for parallel scheduling (R12)."""

from __future__ import annotations

from cairn.graph.builder import BuiltGraph
from cairn.loader.refs import parse_dep_expr
from cairn.model.project import Project


def node_upstream_ids(project: Project, graph: BuiltGraph, node_id: str) -> frozenset[str]:
    node = next(n for n in graph.nodes if n.node_id == node_id)
    if node.kind == "map":
        return frozenset()
    step = project.steps[node.step]
    assert step.inputs is not None
    upstream: set[str] = set()
    for expr in step.inputs:
        dep = parse_dep_expr(expr)
        if dep.kind == "ref":
            upstream.update(n.node_id for n in graph.nodes if n.step == dep.name)
    return frozenset(upstream)


def compute_node_levels(project: Project, graph: BuiltGraph) -> tuple[tuple[str, ...], ...]:
    """Partition nodes into levels for level-parallel execution."""
    deps = {n.node_id: node_upstream_ids(project, graph, n.node_id) for n in graph.nodes}
    remaining = {n.node_id for n in graph.nodes}
    completed: set[str] = set()
    levels: list[tuple[str, ...]] = []
    while remaining:
        ready = sorted(nid for nid in remaining if deps[nid].issubset(completed))
        if not ready:
            msg = f"cannot schedule remaining nodes: {sorted(remaining)}"
            raise RuntimeError(msg)
        levels.append(tuple(ready))
        completed.update(ready)
        remaining -= set(ready)
    return tuple(levels)
