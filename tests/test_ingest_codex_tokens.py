"""Codex token accounting ingest tests."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.codex import parse_rollout_file
from server.ingest.adapters.codex_adapter import CodexAdapter
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def test_codex_tokens_fixture_parses(tmp_path: Path) -> None:
    adapter = CodexAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "codex_tokens.jsonl")
    assert parsed is not None
    assert parsed.events
    assert parsed.usage.input_tokens > 0


def test_codex_tokens_parse_is_deterministic(tmp_path: Path) -> None:
    adapter = CodexAdapter(tmp_path, new_ulid())
    path = FIXTURES / "codex_tokens.jsonl"
    first = adapter.parse_path(path)
    second = adapter.parse_path(path)
    assert first is not None and second is not None
    assert first.external_id == second.external_id
    assert first.usage.input_tokens == second.usage.input_tokens
    assert [e.get("event_id") for e in first.events] == [e.get("event_id") for e in second.events]


def test_codex_ingests_custom_tool_call_and_function_call(tmp_path: Path) -> None:
    parsed = parse_rollout_file(FIXTURES / "codex_custom_tool.jsonl", repo_root=tmp_path)
    assert parsed is not None
    assert [t.name for t in parsed.tool_calls] == ["bash", "edit", "bash"]
    results = [e for e in parsed.events if e.get("type") == "tool_result"]
    assert len(results) == 3
    assert "hi" in (results[0].get("result_inline") or results[0].get("text_inline") or "")
