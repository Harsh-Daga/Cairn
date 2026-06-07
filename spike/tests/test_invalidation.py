"""Property tests for selective cache invalidation (§15, Phase 0 exit criteria)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from spike.cache import SpikeCache
from spike.dag import default_project
from spike.executor import build, nodes_that_would_run
from spike.provider import MockProvider

DEMO_ROOT = Path(__file__).resolve().parents[1] / "demo"


@pytest.fixture
def project_copy(tmp_path: Path) -> Path:
    dest = tmp_path / "demo"
    shutil.copytree(DEMO_ROOT, dest, ignore=shutil.ignore_patterns(".cairn", "outputs"))
    return dest


def test_build_twice_spends_zero_tokens(project_copy: Path) -> None:
    project = default_project(project_copy)
    cache = SpikeCache(project_copy / ".cairn")
    provider = MockProvider()

    first = build(project, cache, provider)
    assert first.stats.misses == 5  # 3 map + reduce + single
    assert first.stats.tokens_spent > 0

    second = build(project, cache, provider)
    assert second.stats.hits == 5
    assert second.stats.misses == 0
    assert second.stats.tokens_spent == 0


def test_edit_one_note_invalidates_exactly_one_map_child(project_copy: Path) -> None:
    project = default_project(project_copy)
    cache = SpikeCache(project_copy / ".cairn")
    provider = MockProvider()

    build(project, cache, provider)

    alpha = project_copy / "inputs" / "notes" / "alpha.md"
    edited = alpha.read_text(encoding="utf-8") + "\nNew metric: NPS 62.\n"
    alpha.write_text(edited, encoding="utf-8")

    third = build(project, cache, provider)
    ran = set(nodes_that_would_run(third))

    assert ran == {"summaries:alpha", "synthesis", "report"}
    assert "summaries:beta" not in ran
    assert "summaries:gamma" not in ran
    assert third.stats.hits == 2  # beta + gamma summaries cached


def test_byte_identical_regeneration_halts_downstream_cascade(project_copy: Path) -> None:
    """If upstream output hash unchanged, downstream keys stay stable (§11, R17 #3)."""
    project = default_project(project_copy)
    cache = SpikeCache(project_copy / ".cairn")
    provider = MockProvider()

    first = build(project, cache, provider)
    synthesis_key = next(r.action_key for r in first.results if r.node_id == "synthesis")

    # Touch spec without changing bytes — no invalidation
    spec = project_copy / "inputs" / "spec.md"
    spec.write_bytes(spec.read_bytes())

    second = build(project, cache, provider)
    assert second.stats.tokens_spent == 0
    second_synthesis_key = next(r.action_key for r in second.results if r.node_id == "synthesis")
    assert synthesis_key == second_synthesis_key
