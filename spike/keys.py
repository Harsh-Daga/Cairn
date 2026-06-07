"""Action-key computation for spike chat nodes (§9, R1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from spike.canonical import CAIRN_KEY_VERSION, hash_bytes, hash_obj, merkle_hash


@dataclass(frozen=True)
class PromptRef:
    path: str
    body: bytes
    front_matter: dict[str, Any]


@dataclass(frozen=True)
class ActionKeyInput:
    kind: str
    prompt: PromptRef
    model: str
    params: dict[str, Any]
    input_digests: tuple[str, ...]
    sample_index: int = 0


def normalize_front_matter(front_matter: dict[str, Any]) -> dict[str, Any]:
    """Normalize prompt front matter for stable keying."""
    return {str(k): v for k, v in sorted(front_matter.items(), key=lambda pair: str(pair[0]))}


def rendered_inputs_hash(input_digests: tuple[str, ...]) -> str:
    return merkle_hash(*input_digests)


def action_key_payload(data: ActionKeyInput) -> dict[str, Any]:
    """Build the pre-hash action-key object (§9)."""
    payload: dict[str, Any] = {
        "cairn_key_version": CAIRN_KEY_VERSION,
        "kind": data.kind,
        "prompt_hash": hash_bytes(data.prompt.body),
        "prompt_front_matter": normalize_front_matter(data.prompt.front_matter),
        "model": data.model,
        "params": data.params,
        "tools": [],
        "sub_agents": [],
        "budget": {},
        "rendered_inputs_hash": rendered_inputs_hash(data.input_digests),
    }
    if data.sample_index:
        payload["sample_index"] = data.sample_index
    return payload


def action_key(data: ActionKeyInput) -> str:
    """Compute the action key for a node."""
    return hash_obj(action_key_payload(data))
