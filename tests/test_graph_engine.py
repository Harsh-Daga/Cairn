"""Phase 10 execution graph engine tests."""

from __future__ import annotations

from cairn.graph.engine import (
    build_artifact_graph,
    build_artifact_graph_from_files,
    build_dependency_graph,
    build_execution_graph,
)
from cairn.model.artifact import Artifact, LineageEdge


def test_build_execution_graph_tags_kind() -> None:
    events = [
        {"seq": 1, "type": "user_prompt", "text_inline": "hi"},
        {"seq": 2, "type": "assistant_message", "text_inline": "hello"},
    ]
    graph = build_execution_graph(events)
    assert graph["graph_kind"] == "execution"
    assert len(graph["nodes"]) == 2


def test_build_artifact_graph_lineage() -> None:
    a = Artifact("hash-a", "file", "a.txt", None, None, None, None, {})
    b = Artifact("hash-b", "report", "out.md", None, None, None, None, {})
    graph = build_artifact_graph(
        [a, b],
        [LineageEdge("derived_from", "hash-b", "hash-a")],
    )
    assert graph["graph_kind"] == "artifact"
    assert len(graph["edges"]) == 1
    assert graph["edges"][0]["kind"] == "derived_from"


def test_build_artifact_graph_from_files() -> None:
    rows = [
        {"path_rel": "src/a.py", "before_hash": "h1", "after_hash": "h2"},
        {"path_rel": "src/b.py", "before_hash": None, "after_hash": "h3"},
    ]
    graph = build_artifact_graph_from_files(rows)
    assert graph["graph_kind"] == "artifact"
    assert len(graph["nodes"]) == 2


def test_build_dependency_graph(project_dir: object) -> None:
    from cairn.loader.toml import load_project

    project = load_project(project_dir)
    graph = build_dependency_graph(project)
    assert graph["graph_kind"] == "dependency"
    assert "summaries" in {n["id"] for n in graph["nodes"] if n.get("type") == "step"}
    assert graph["edges"]
