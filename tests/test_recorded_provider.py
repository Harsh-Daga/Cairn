"""RecordedProvider uses stable sha256, not builtin hash()."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cairn.model.messages import CompletionRequest, Message, TextBlock
from cairn.providers.recorded import RecordedProvider, _request_key


@pytest.mark.asyncio
async def test_recorded_output_stable_across_instances(tmp_path: Path) -> None:
    fixtures = tmp_path / "fx"
    req = CompletionRequest(
        model="gpt-4o-mini",
        messages=(Message(role="user", content=(TextBlock(text="hello"),)),),
        params={"max_tokens": 10},
        provider="openai",
    )
    key = _request_key(req)
    p1 = RecordedProvider(fixtures, record=True)
    r1 = await p1.complete(req)
    p2 = RecordedProvider(fixtures, record=False)
    r2 = await p2.complete(req)
    assert r1.text == r2.text
    assert (fixtures / f"{key}.json").is_file()
    data = json.loads((fixtures / f"{key}.json").read_text(encoding="utf-8"))
    assert data["text"].startswith("[recorded:")
