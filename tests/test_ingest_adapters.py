"""Smoke tests for additional ingest adapters."""

from __future__ import annotations

from pathlib import Path

from server.ingest.adapters.codex_adapter import CodexAdapter
from server.ingest.adapters.gemini_adapter import GeminiAdapter
from server.ingest.adapters.generic_jsonl_adapter import AiderAdapter, GooseAdapter, OpenCodeAdapter
from server.ingest.adapters.hermes_adapter import HermesAdapter
from server.ingest.adapters.openclaw_adapter import OpenClawAdapter
from server.util.ids import new_ulid

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"


def test_codex_fixture_parses(tmp_path: Path) -> None:
    adapter = CodexAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "codex_mini.jsonl")
    assert parsed is not None
    assert parsed.events


def test_gemini_fixture_parses(tmp_path: Path) -> None:
    adapter = GeminiAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "gemini_mini.jsonl")
    assert parsed is not None


def test_hermes_fixture_parses(tmp_path: Path) -> None:
    adapter = HermesAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "hermes_mini.json")
    assert parsed is not None


def test_openclaw_fixture_parses(tmp_path: Path) -> None:
    adapter = OpenClawAdapter(tmp_path, new_ulid())
    parsed = adapter.parse_path(FIXTURES / "openclaw_mini.jsonl")
    assert parsed is not None


def test_agent_jsonl_fixture_parses(tmp_path: Path) -> None:
    for cls in (AiderAdapter, GooseAdapter, OpenCodeAdapter):
        adapter = cls(tmp_path, new_ulid())
        parsed = adapter.parse_path(FIXTURES / "agent_jsonl_mini.jsonl")
        assert parsed is not None
