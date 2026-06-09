"""Execution, artifact, and dependency graph builders (Phase 10)."""

from __future__ import annotations

from typing import Any

from cairn.graph.builder import build_graph
from cairn.graph.session_graph import build_session_graph
from cairn.loader.refs import parse_dep_expr
from cairn.model.artifact import Artifact, LineageEdge
from cairn.model.project import Project


def build_execution_graph(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Infer execution DAG from session events (alias of capture micro graph)."""
    return {**build_session_graph(events), "graph_kind": "execution"}


def build_artifact_graph(
    artifacts: list[Artifact],
    lineage: list[LineageEdge] | None = None,
) -> dict[str, Any]:
    """Build artifact DAG from registry artifacts and lineage edges."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    for artifact in artifacts:
        nodes.append(
            {
                "id": artifact.content_hash,
                "type": artifact.kind,
                "label": artifact.path_rel or artifact.content_hash[:12],
                "path_rel": artifact.path_rel,
            }
        )
    for edge in lineage or []:
        edges.append(
            {
                "from": edge.from_id,
                "to": edge.to_id,
                "kind": edge.relation,
            }
        )
    if not edges and len(artifacts) > 1:
        by_path = {a.path_rel: a.content_hash for a in artifacts if a.path_rel}
        paths = sorted(by_path.keys())
        for left, right in zip(paths, paths[1:], strict=False):
            edges.append(
                {
                    "from": by_path[left],
                    "to": by_path[right],
                    "kind": "derived_from",
                }
            )
    return {
        "nodes": nodes,
        "edges": edges,
        "graph_kind": "artifact",
    }


def build_artifact_graph_from_files(
    file_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build artifact graph from capture file_artifacts rows."""
    artifacts: list[Artifact] = []
    for row in file_rows:
        path_rel = row.get("path_rel")
        if not isinstance(path_rel, str):
            continue
        content_hash = row.get("after_hash") or row.get("before_hash") or path_rel
        artifacts.append(
            Artifact(
                content_hash=str(content_hash),
                kind="file",
                path_rel=path_rel,
                mime=None,
                run_id=None,
                session_id=None,
                size_bytes=None,
                metadata={
                    "before_hash": row.get("before_hash"),
                    "after_hash": row.get("after_hash"),
                },
            )
        )
    return build_artifact_graph(artifacts)


def build_dependency_graph(project: Project) -> dict[str, Any]:
    """Build workflow step dependency DAG from cairn.toml."""
    graph = build_graph(project)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    step_nodes = {node.step for node in graph.nodes}
    for step_name in project.steps:
        nodes.append({"id": step_name, "type": "step", "label": step_name})
    for step_name, step in project.steps.items():
        if step.over is not None:
            dep = parse_dep_expr(step.over)
            if dep.kind == "ref" and dep.name in step_nodes:
                edges.append({"from": dep.name, "to": step_name, "kind": "depends_on"})
        elif step.inputs:
            for expr in step.inputs:
                dep = parse_dep_expr(expr)
                if dep.kind == "ref" and dep.name in step_nodes:
                    edges.append({"from": dep.name, "to": step_name, "kind": "depends_on"})
    for node in graph.nodes:
        nodes.append(
            {
                "id": node.node_id,
                "type": node.kind,
                "label": node.node_id,
                "step": node.step,
            }
        )
        edges.append({"from": node.step, "to": node.node_id, "kind": "expands_to"})
    return {
        "nodes": nodes,
        "edges": edges,
        "graph_kind": "dependency",
        "topo_order": list(graph.topo_order),
    }
