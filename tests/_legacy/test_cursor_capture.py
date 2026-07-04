"""Parser and ingest smoke tests for Cursor and Hermes."""

from __future__ import annotations

import json
from pathlib import Path

from cairn.ingest.normalizer import assign_seq
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.parsers.cursor import parse_transcript_file
from cairn.ingest.parsers.hermes import parse_session_file
from cairn.ingest.writer import CaptureWriter
from cairn.ledger.resolve import hash_obj

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"
CURSOR_FIXTURE = FIXTURES / "cursor_mini.jsonl"
HERMES_FIXTURE = FIXTURES / "hermes_mini.json"
CLAUDE_FIXTURE = FIXTURES / "claude_code_mini.jsonl"


def test_cursor_parser_golden_events() -> None:
    repo = Path("/tmp/cairn-cursor-fixture")
    repo.mkdir(parents=True, exist_ok=True)
    parsed = parse_transcript_file(
        CURSOR_FIXTURE,
        repo_root=repo,
        external_id="cursor-sess-redacted",
    )
    assert parsed is not None
    assert parsed.external_id == "cursor-sess-redacted"

    events = assign_seq([{k: v for k, v in e.items() if k != "line_no"} for e in parsed.events])
    assert events[0]["type"] == "user_prompt"
    assert events[0]["text_hash"] == hash_obj("Fix the cursor parser test")
    assert events[1]["type"] == "assistant_message"
    tool_call = next(e for e in events if e["type"] == "tool_call")
    assert tool_call["name"] == "edit"
    assert len(parsed.file_artifacts) == 1
    assert parsed.file_artifacts[0].path_rel == "src/app.py"


def test_cursor_ingest_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_transcript_file(
        CURSOR_FIXTURE,
        repo_root=repo,
        external_id="cursor-idem",
    )
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        first = writer.ingest_cursor_session(parsed)
        second = writer.ingest_cursor_session(parsed)
        assert first.inserted is True
        assert second.inserted is False
        row = writer.connection.execute(
            "SELECT has_cost FROM runs WHERE run_id = ?", (first.run_id,)
        ).fetchone()
        assert row["has_cost"] == 0
    finally:
        writer.close()


def test_hermes_parser_golden_events() -> None:
    repo = Path("/tmp/cairn-hermes-fixture")
    repo.mkdir(parents=True, exist_ok=True)
    parsed = parse_session_file(HERMES_FIXTURE, repo_root=repo)
    assert parsed is not None
    assert parsed.external_id == "hermes-sess-redacted"
    assert parsed.model == "hermes-test"

    events = assign_seq([{k: v for k, v in e.items() if k != "msg_idx"} for e in parsed.events])
    assert events[0]["type"] == "user_prompt"
    assert events[0]["text_hash"] == hash_obj("Fix the hermes parser test")
    assert events[1]["type"] == "assistant_message"
    tool_call = next(e for e in events if e["type"] == "tool_call")
    assert tool_call["name"] == "edit"
    assert events[-1]["type"] == "tool_result"
    assert len(parsed.file_artifacts) == 1
    assert parsed.file_artifacts[0].path_rel == "src/app.py"


def test_hermes_ingest_idempotent(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    (repo / "src").mkdir(parents=True)
    target = repo / "src" / "app.py"
    data = json.loads(HERMES_FIXTURE.read_text(encoding="utf-8"))
    tool_call = data["messages"][1]["tool_calls"][0]
    args = json.loads(tool_call["function"]["arguments"])
    args["path"] = str(target)
    tool_call["function"]["arguments"] = json.dumps(args)
    session_file = tmp_path / "session.json"
    session_file.write_text(json.dumps(data), encoding="utf-8")
    parsed = parse_session_file(session_file, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        first = writer.ingest_hermes_session(parsed)
        second = writer.ingest_hermes_session(parsed)
        assert first.inserted is True
        assert second.inserted is False
    finally:
        writer.close()


def test_claude_ingest_roundtrip(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        result = writer.ingest_claude_session(parsed)
        events = writer.load_events(result.run_id)
        assert len(events) >= 4
    finally:
        writer.close()
