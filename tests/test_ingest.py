"""Phase 3 capture ingest tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.ingest.normalizer import assign_seq
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.ledger.resolve import hash_obj
from cairn.ledger.schema import SCHEMA_VERSION

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"
CLAUDE_FIXTURE = FIXTURES / "claude_code_mini.jsonl"


def test_schema_version_is_one() -> None:
    assert SCHEMA_VERSION == 8


def test_claude_parser_golden_events() -> None:
    repo = Path("/tmp/cairn-fixture")
    repo.mkdir(parents=True, exist_ok=True)
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    assert parsed.external_id == "sess-redacted-001"
    assert parsed.git_branch == "main"
    assert parsed.usage.usage.input_tokens == 10
    assert parsed.usage.usage.output_tokens == 5

    events = assign_seq([{k: v for k, v in e.items() if k != "line_no"} for e in parsed.events])
    assert len(events) == 4
    assert events[0]["type"] == "user_prompt"
    assert events[0]["text_hash"] == hash_obj("Fix the parser test")
    assert events[0]["text_inline"] == "Fix the parser test"
    assert events[1]["type"] == "assistant_message"
    assert events[1]["model"] == "claude-test"
    assert events[2]["type"] == "tool_call"
    assert events[2]["tool_use_id"] == "toolu_01"
    assert events[2]["name"] == "Edit"
    assert events[3]["type"] == "tool_result"
    assert events[3]["tool_use_id"] == "toolu_01"
    assert events[3]["result_inline"] == "OK"

    assert len(parsed.file_artifacts) == 1
    assert parsed.file_artifacts[0].path_rel == "src/app.py"


def test_ingest_twice_one_runs_row(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    (repo / "src").mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None

    writer = CaptureWriter(repo)
    try:
        first = writer.ingest_claude_session(parsed)
        second = writer.ingest_claude_session(parsed)
        assert first.inserted is True
        assert second.inserted is False
        assert first.run_id == second.run_id

        count = writer.connection.execute(
            "SELECT COUNT(*) FROM runs WHERE source = 'claude-code' AND external_id = ?",
            (parsed.external_id,),
        ).fetchone()[0]
        assert count == 1

        event_count = writer.connection.execute(
            "SELECT COUNT(*) FROM events WHERE run_id = ?",
            (first.run_id,),
        ).fetchone()[0]
        assert event_count == 4
    finally:
        writer.close()


def test_sessions_list(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
        sessions = writer.list_sessions(limit=10)
        assert len(sessions) == 1
        assert sessions[0].external_id == "sess-redacted-001"
        assert sessions[0].event_count == 4
    finally:
        writer.close()


def test_load_events(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        result = writer.ingest_claude_session(parsed)
        events = writer.load_events(result.run_id)
        assert len(events) == 4
        assert events[0]["type"] == "user_prompt"
    finally:
        writer.close()


def test_parse_since() -> None:
    from cairn.ingest.project_paths import parse_since

    cutoff = parse_since("7d")
    assert cutoff.tzinfo is not None


def test_parse_since_invalid() -> None:
    from cairn.ingest.project_paths import parse_since

    with pytest.raises(ValueError):
        parse_since("bad")


def test_discover_claude_jsonl_nested_and_subagents(tmp_path: Path) -> None:
    from cairn.ingest.project_paths import discover_claude_jsonl

    base = tmp_path / "claude-project"
    base.mkdir()
    top = base / "aaa.jsonl"
    top.write_text("{}\n", encoding="utf-8")
    nested = base / "bbb" / "bbb.jsonl"
    nested.parent.mkdir()
    nested.write_text("{}\n", encoding="utf-8")
    subagent = base / "ccc" / "subagents" / "agent-xyz.jsonl"
    subagent.parent.mkdir(parents=True)
    subagent.write_text("{}\n", encoding="utf-8")

    found = discover_claude_jsonl(tmp_path, claude_project_dir=base)
    assert {p.name for p in found} == {"aaa.jsonl", "bbb.jsonl", "agent-xyz.jsonl"}


def test_rollup_same_day_different_models_no_unique_violation(tmp_path: Path) -> None:
    """Ingesting multiple models on one day must not fail rollup_daily UNIQUE."""
    repo = tmp_path / "proj"
    repo.mkdir()

    base = CLAUDE_FIXTURE.read_text(encoding="utf-8")
    first_path = tmp_path / "sess-a.jsonl"
    first_path.write_text(base.replace("sess-redacted-001", "sess-a"), encoding="utf-8")
    second_path = tmp_path / "sess-b.jsonl"
    second_path.write_text(
        base.replace("sess-redacted-001", "sess-b").replace("claude-test", "claude-other"),
        encoding="utf-8",
    )

    parsed_a = parse_jsonl_file(first_path, repo_root=repo)
    parsed_b = parse_jsonl_file(second_path, repo_root=repo)
    assert parsed_a is not None and parsed_b is not None
    assert parsed_a.model == "claude-test"
    assert parsed_b.model == "claude-other"

    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed_a)
        writer.ingest_claude_session(parsed_b)

        rows = writer.connection.execute(
            """
            SELECT model, sessions FROM rollup_daily
            WHERE day = '2026-06-01' AND source = 'claude-code'
            ORDER BY model
            """
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["sessions"] == 1
        assert rows[1]["sessions"] == 1
    finally:
        writer.close()


def test_subagent_external_id_unique(tmp_path: Path) -> None:
    repo = Path("/tmp/cairn-fixture")
    repo.mkdir(parents=True, exist_ok=True)
    subagent = (
        tmp_path
        / "proj"
        / "2c139dae-bdef-46f8-b328-b2f54ef450f6"
        / "subagents"
        / "agent-a9aa01b.jsonl"
    )
    subagent.parent.mkdir(parents=True)
    subagent.write_text(
        CLAUDE_FIXTURE.read_text(encoding="utf-8").replace(
            "sess-redacted-001",
            "2c139dae-bdef-46f8-b328-b2f54ef450f6",
        ),
        encoding="utf-8",
    )
    parsed = parse_jsonl_file(subagent, repo_root=repo)
    assert parsed is not None
    assert parsed.external_id == ("2c139dae-bdef-46f8-b328-b2f54ef450f6#subagent:agent-a9aa01b")
