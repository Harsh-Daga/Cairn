"""Phase 8 agent integration framework tests."""

from __future__ import annotations

from pathlib import Path

from cairn.agents.registry import AGENT_SOURCES, get_parser, list_agent_sources
from cairn.agents.replay import replay_session
from cairn.ingest.parsers.aider import parse_aider_jsonl
from cairn.ingest.parsers.goose import parse_goose_jsonl
from cairn.ingest.parsers.openhands import parse_openhands_jsonl
from cairn.ingest.writer import CaptureWriter

FIXTURE = Path(__file__).parent / "fixtures" / "ingest" / "agent_jsonl_mini.jsonl"


def test_agent_registry_lists_all_sources() -> None:
    sources = list_agent_sources()
    assert "aider" in sources
    assert "openhands" in sources
    assert "goose" in sources
    assert len(sources) == len(AGENT_SOURCES)


def test_parse_aider_jsonl() -> None:
    repo = Path("/tmp/cairn-fixture")
    parsed = parse_aider_jsonl(FIXTURE, repo_root=repo)
    assert parsed is not None
    assert parsed.source == "aider"
    assert parsed.external_id == "agent-mini-001"
    assert any(e.get("type") == "tool_call" for e in parsed.events)


def test_parse_openhands_and_goose() -> None:
    repo = Path("/tmp/cairn-fixture")
    oh = parse_openhands_jsonl(FIXTURE, repo_root=repo)
    goose = parse_goose_jsonl(FIXTURE, repo_root=repo)
    assert oh is not None and oh.source == "openhands"
    assert goose is not None and goose.source == "goose"


def test_ingest_agent_session(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    writer = CaptureWriter(repo)
    try:
        parsed = parse_aider_jsonl(FIXTURE, repo_root=repo)
        assert parsed is not None
        result = writer.ingest_agent_session(parsed)
        assert result.inserted
        assert result.event_count > 0
    finally:
        writer.close()


def test_registry_parser_dispatch() -> None:
    parser = get_parser("aider")
    parsed = parser.parse(FIXTURE, repo_root=Path("/tmp/cairn-fixture"))
    assert parsed is not None
    assert parsed.external_id == "agent-mini-001"


def test_replay_session_after_ingest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    writer = CaptureWriter(repo)
    try:
        parsed = parse_aider_jsonl(FIXTURE, repo_root=repo)
        assert parsed is not None
        writer.ingest_agent_session(parsed)
    finally:
        writer.close()
    index = replay_session(repo, "agent-mini-001")
    assert index.is_file()
