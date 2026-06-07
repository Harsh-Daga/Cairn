"""Action-key computation (§9, R1, ADR 0005)."""

from __future__ import annotations

from typing import Any

from cairn.model.nodes import Node
from cairn.util.canonical import CAIRN_KEY_VERSION, hash_bytes, hash_obj, merkle_hash

_KEY_EXCLUDED_PARAMS = frozenset({"temperature"})


def params_for_key(params: dict[str, Any]) -> dict[str, Any]:
    """Params included in the action key (temperature excluded per §9)."""
    return {k: v for k, v in params.items() if k not in _KEY_EXCLUDED_PARAMS}


def rendered_inputs_hash(input_digests: tuple[str, ...]) -> str:
    return merkle_hash(*input_digests)


def action_key_payload(node: Node) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "cairn_key_version": CAIRN_KEY_VERSION,
        "kind": node.cache_kind,
        "prompt_hash": hash_bytes(node.prompt.template_body_bytes),
        "system_hash": hash_bytes(node.system.encode("utf-8")),
        "model": node.model,
        "params": params_for_key(node.params),
        "tools": [],
        "sub_agents": [],
        "budget": {},
        "rendered_inputs_hash": rendered_inputs_hash(node.input_digests),
    }
    if node.sample_index:
        payload["sample_index"] = node.sample_index
    return payload


def action_key(node: Node) -> str:
    return hash_obj(action_key_payload(node))
