"""Action-key stability tests (§9)."""

from __future__ import annotations

from spike.canonical import hash_bytes
from spike.keys import ActionKeyInput, PromptRef, action_key


def test_action_key_changes_when_input_changes() -> None:
    prompt = PromptRef(path="p.md", body=b"body", front_matter={"description": "d"})
    base = ActionKeyInput(
        kind="chat",
        prompt=prompt,
        model="gpt-4o-mini",
        params={"max_tokens": 500},
        input_digests=(hash_bytes(b"a"),),
    )
    other = ActionKeyInput(
        kind="chat",
        prompt=prompt,
        model="gpt-4o-mini",
        params={"max_tokens": 500},
        input_digests=(hash_bytes(b"b"),),
    )
    assert action_key(base) != action_key(other)


def test_action_key_stable_for_same_inputs() -> None:
    prompt = PromptRef(path="p.md", body=b"body", front_matter={})
    data = ActionKeyInput(
        kind="chat",
        prompt=prompt,
        model="gpt-4o-mini",
        params={"max_tokens": 500},
        input_digests=(hash_bytes(b"same"),),
    )
    assert action_key(data) == action_key(data)
