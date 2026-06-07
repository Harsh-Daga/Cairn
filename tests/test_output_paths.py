"""Output path Jinja rendering (§6.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.model.errors import OutputCollisionError


def test_output_path_uses_item_name(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace(
            "outputs/summaries/{{ item.stem }}.md",
            "outputs/summaries/{{ item.name }}",
        ),
        encoding="utf-8",
    )
    project = load_project(project_dir)
    graph = build_graph(project)
    paths = {n.output_path for n in graph.nodes if n.kind == "map"}
    assert paths == {
        "outputs/summaries/alpha.md",
        "outputs/summaries/beta.md",
        "outputs/summaries/gamma.md",
    }


def test_output_path_whitespace_jinja(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace(
            "outputs/summaries/{{ item.stem }}.md",
            "outputs/summaries/{{  item.stem  }}.md",
        ),
        encoding="utf-8",
    )
    project = load_project(project_dir)
    graph = build_graph(project)
    assert any(n.output_path == "outputs/summaries/alpha.md" for n in graph.nodes)


def test_output_path_collision_still_detected(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace(
            "outputs/summaries/{{ item.stem }}.md",
            "outputs/summaries/same.md",
        ),
        encoding="utf-8",
    )
    project = load_project(project_dir)
    with pytest.raises(OutputCollisionError):
        build_graph(project)
