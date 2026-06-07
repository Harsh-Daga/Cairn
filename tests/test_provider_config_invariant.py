"""R18 boundary: provider/credential config must not affect action keys (ADR 0002/0004)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.plan.action_key import action_key
from cairn.plan.planner import plan_build


class _EmptyCache:
    def get_output_hash(self, key: str) -> str | None:
        return None

    def has_blob(self, digest: str) -> bool:
        return False


def test_action_keys_unchanged_when_env_credentials_change(
    project_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = load_project(project_dir)
    graph = build_graph(project)
    keys_before = tuple(
        action_key(p.node) for p in plan_build(project, graph, _EmptyCache()).nodes
    )

    monkeypatch.setenv("OLLAMA_CLOUD_API_KEY", "key-a")
    monkeypatch.setenv("OLLAMA_CLOUD_BASE_URL", "https://custom.example.com")
    keys_after = tuple(
        action_key(p.node) for p in plan_build(project, graph, _EmptyCache()).nodes
    )
    assert keys_before == keys_after
