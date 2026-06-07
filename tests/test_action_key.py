"""Golden-hash and stability tests for action keys (§9, ADR 0005)."""

from __future__ import annotations

from cairn.model.nodes import Node
from cairn.model.project import Prompt
from cairn.model.system import DEFAULT_SYSTEM_PROMPT
from cairn.plan.action_key import action_key, action_key_payload
from cairn.util.canonical import hash_bytes


def _sample_node(**overrides: object) -> Node:
    prompt = Prompt(
        path="prompts/summarize.md",
        template_body="Summarize {{ item.content }}\n",
        template_body_bytes=b"Summarize {{ item.content }}\n",
        front_matter={"description": "meta only"},
        model_override=None,
        params_override={},
    )
    base = Node(
        node_id="summaries:alpha",
        step="summaries",
        kind="map",
        prompt=prompt,
        model="gpt-4o-mini",
        params={"max_tokens": 500, "temperature": 0.0},
        materialization="cached",
        output_path="outputs/summaries/alpha.md",
        item=None,
        input_digests=(hash_bytes(b"note-bytes"),),
        declared_refs=(),
        declared_sources=("notes",),
        system=DEFAULT_SYSTEM_PROMPT,
    )
    if overrides:
        return Node(**{**base.__dict__, **overrides})
    return base


def test_action_key_golden_vector() -> None:
    payload = action_key_payload(_sample_node())
    digest = action_key(_sample_node())
    assert digest == "7065b2c8256d09ed6fc082b5c709ae73d36c525d3adf60f128025f06269f77f5"
    assert payload["system_hash"] == hash_bytes(DEFAULT_SYSTEM_PROMPT.encode("utf-8"))
    assert payload["prompt_hash"] == hash_bytes(b"Summarize {{ item.content }}\n")
    assert "prompt_front_matter" not in payload
    assert "temperature" not in payload["params"]


def test_action_key_changes_when_input_changes() -> None:
    a = _sample_node(input_digests=(hash_bytes(b"a"),))
    b = _sample_node(input_digests=(hash_bytes(b"b"),))
    assert action_key(a) != action_key(b)


def test_action_key_stable_for_same_inputs() -> None:
    node = _sample_node()
    assert action_key(node) == action_key(node)


def test_description_front_matter_not_in_key() -> None:
    p1 = Prompt(
        path="p.md",
        template_body="Hello\n",
        template_body_bytes=b"Hello\n",
        front_matter={"description": "v1"},
        model_override=None,
        params_override={},
    )
    p2 = Prompt(
        path="p.md",
        template_body="Hello\n",
        template_body_bytes=b"Hello\n",
        front_matter={"description": "v2"},
        model_override=None,
        params_override={},
    )
    n1 = _sample_node(prompt=p1)
    n2 = _sample_node(prompt=p2)
    assert action_key(n1) == action_key(n2)
