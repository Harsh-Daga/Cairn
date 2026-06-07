"""Property tests for R17 invariants #1–#3, #8, #9, #12."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from cairn.cache.store import CacheStore
from cairn.executor.runner import BuildOptions, run_build_sync
from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.model.errors import (
    CycleError,
    OutputCollisionError,
    UndeclaredRefError,
    ValidationError,
)
from cairn.providers.recorded import RecordedProvider


def _build(project_dir: Path, fixtures_dir: Path) -> object:
    project = load_project(project_dir)
    graph = build_graph(project)
    cache = CacheStore(project.root)
    provider = RecordedProvider(fixtures_dir)
    try:
        return run_build_sync(
            project,
            graph,
            cache,
            provider,
            BuildOptions(yes=True),
        )
    finally:
        cache.close()


def test_r17_1_build_twice_zero_tokens(project_dir: Path, fixtures_dir: Path) -> None:
    first = _build(project_dir, fixtures_dir)
    second = _build(project_dir, fixtures_dir)
    assert first.stats.misses == 5
    assert first.stats.tokens_spent > 0
    assert second.stats.hits == 5
    assert second.stats.misses == 0
    assert second.stats.tokens_spent == 0


def test_r17_2_edit_one_map_input(project_dir: Path, fixtures_dir: Path) -> None:
    _build(project_dir, fixtures_dir)
    alpha = project_dir / "inputs" / "notes" / "alpha.md"
    alpha.write_text(alpha.read_text(encoding="utf-8") + "\nEdit.\n", encoding="utf-8")
    result = _build(project_dir, fixtures_dir)
    ran = {n.node_id for n in result.nodes if not n.cache_hit}
    assert ran == {"summaries:alpha", "synthesis", "report"}
    assert result.stats.hits == 2


def test_r17_3_byte_identical_halts_cascade(project_dir: Path, fixtures_dir: Path) -> None:
    first = _build(project_dir, fixtures_dir)
    synth_key = next(n.action_key for n in first.nodes if n.node_id == "synthesis")
    spec = project_dir / "inputs" / "spec.md"
    spec.write_bytes(spec.read_bytes())
    second = _build(project_dir, fixtures_dir)
    assert second.stats.tokens_spent == 0
    second_key = next(n.action_key for n in second.nodes if n.node_id == "synthesis")
    assert synth_key == second_key


def test_r17_8_empty_map_source(project_dir: Path, fixtures_dir: Path) -> None:
    notes = project_dir / "inputs" / "notes"
    shutil.rmtree(notes)
    notes.mkdir()
    project = load_project(project_dir)
    graph = build_graph(project)
    assert sum(1 for n in graph.nodes if n.kind == "map") == 0
    result = _build(project_dir, fixtures_dir)
    assert result.stats.misses == 2  # synthesis + report only


def test_r17_9_cycle_is_validate_error(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        text
        + """
[steps.loop_b]
prompt = "prompts/polish.md"
inputs = ["ref('loop_a')"]
output = "outputs/loop_b.md"

[steps.loop_a]
prompt = "prompts/polish.md"
inputs = ["ref('loop_b')"]
output = "outputs/loop_a.md"
""",
        encoding="utf-8",
    )
    project = load_project(project_dir)
    with pytest.raises(CycleError):
        build_graph(project)


def test_r17_9_missing_ref_validate_error(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        text.replace(
            'inputs = ["ref(\'synthesis\')"]',
            'inputs = ["ref(\'missing_step\')"]',
        ),
        encoding="utf-8",
    )
    project = load_project(project_dir)
    with pytest.raises(ValidationError):
        build_graph(project)


def test_r17_12_output_collision(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    text = toml.read_text(encoding="utf-8")
    toml.write_text(
        text.replace(
            "outputs/summaries/{{ item.stem }}.md",
            "outputs/summaries/same.md",
        ),
        encoding="utf-8",
    )
    project = load_project(project_dir)
    with pytest.raises(OutputCollisionError):
        build_graph(project)


def test_undeclared_template_ref_fails_validate(project_dir: Path) -> None:
    prompt = project_dir / "prompts" / "polish.md"
    prompt.write_text(
        prompt.read_text(encoding="utf-8") + "\n{{ source('notes') }}\n",
        encoding="utf-8",
    )
    project = load_project(project_dir)
    with pytest.raises(UndeclaredRefError):
        build_graph(project)
