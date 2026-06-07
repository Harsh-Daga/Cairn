"""System prompt action-key tests (ADR 0007)."""

from __future__ import annotations

from pathlib import Path

from cairn.graph.builder import build_graph
from cairn.loader.toml import load_project
from cairn.model.system import DEFAULT_SYSTEM_PROMPT
from cairn.plan.action_key import action_key, action_key_payload
from cairn.plan.planner import plan_build
from cairn.util.canonical import hash_bytes
from tests.test_action_key import _sample_node


class _EmptyCache:
    def get_output_hash(self, key: str) -> str | None:
        return None

    def has_blob(self, digest: str) -> bool:
        return False


def test_system_hash_in_payload() -> None:
    payload = action_key_payload(_sample_node())
    assert payload["system_hash"] == hash_bytes(DEFAULT_SYSTEM_PROMPT.encode("utf-8"))


def test_changing_system_changes_key() -> None:
    a = _sample_node(system=DEFAULT_SYSTEM_PROMPT)
    b = _sample_node(system="You are a terse editor.")
    assert action_key(a) != action_key(b)


def test_default_system_stable() -> None:
    node = _sample_node()
    assert action_key(node) == action_key(_sample_node())


def test_project_defaults_system_changes_keys(project_dir: Path) -> None:
    toml = project_dir / "cairn.toml"
    base_text = toml.read_text(encoding="utf-8")
    project_a = load_project(project_dir)
    graph_a = build_graph(project_a)
    keys_a = tuple(p.action_key for p in plan_build(project_a, graph_a, _EmptyCache()).nodes)

    toml.write_text(
        base_text.replace(
            'model = "ollama-cloud/kimi-k2.6:cloud"',
            'model = "ollama-cloud/kimi-k2.6:cloud"\nsystem = "Custom project system."',
        ),
        encoding="utf-8",
    )
    project_b = load_project(project_dir)
    graph_b = build_graph(project_b)
    keys_b = tuple(p.action_key for p in plan_build(project_b, graph_b, _EmptyCache()).nodes)
    assert keys_a != keys_b
