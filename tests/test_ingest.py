"""Phase 3 capture ingest tests (R19.3, invariants 18 & 20)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cairn.ingest.normalizer import assign_seq
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.ledger.schema import SCHEMA_VERSION, migrate
from cairn.util.canonical import hash_obj
from tests.test_ledger import _legacy_ac_only_db

FIXTURES = Path(__file__).parent / "fixtures" / "ingest"
CLAUDE_FIXTURE = FIXTURES / "claude_code_mini.jsonl"


def test_schema_version_is_three() -> None:
    assert SCHEMA_VERSION == 3


def test_migrate_v2_to_v3_adds_capture_tables(tmp_path: Path) -> None:
    db = tmp_path / "ledger.db"
    _legacy_ac_only_db(db)
    conn = sqlite3.connect(db)
    migrate(conn)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == 3
    cols = {r[1] for r in conn.execute("PRAGMA table_info(runs)").fetchall()}
    assert {"kind", "source", "external_id", "trajectory_hash"} <= cols
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    assert {"events", "file_artifacts"} <= tables
    kind = conn.execute("SELECT kind FROM runs").fetchall()
    assert not kind
    conn.close()


def test_claude_parser_golden_events() -> None:
    repo = Path("/tmp/cairn-fixture")
    repo.mkdir(parents=True, exist_ok=True)
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    assert parsed.external_id == "sess-redacted-001"
    assert parsed.git_branch == "main"
    assert parsed.usage.usage.input_tokens == 10
    assert parsed.usage.usage.output_tokens == 5

    events = assign_seq(
        [{k: v for k, v in e.items() if k != "line_no"} for e in parsed.events]
    )
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

    mirror = repo / ".cairn" / "sessions" / f"{parsed.external_id}.json"
    assert mirror.is_file()


def test_ingest_never_touches_action_cache(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None

    writer = CaptureWriter(repo)
    try:
        writer.connection.execute(
            """
            INSERT INTO action_cache (
              action_key, output_hash, kind, created_at, last_used_at, model
            )
            VALUES ('probe-key', 'deadbeef', 'chat', 't', 't', 'm')
            """
        )
        writer.connection.commit()
        before = writer.connection.execute("SELECT COUNT(*) FROM action_cache").fetchone()[0]

        writer.ingest_claude_session(parsed)
        writer.ingest_claude_session(parsed)

        after = writer.connection.execute("SELECT COUNT(*) FROM action_cache").fetchone()[0]
        row = writer.connection.execute(
            "SELECT output_hash FROM action_cache WHERE action_key = 'probe-key'"
        ).fetchone()
        assert before == after == 1
        assert row[0] == "deadbeef"
    finally:
        writer.close()


def test_sessions_cli_list(tmp_path: Path) -> None:
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


def test_show_loads_trajectory(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
        trajectory = writer.load_trajectory(parsed.external_id)
        assert trajectory is not None
        assert trajectory["schema"] == "cairn-trajectory"
        assert trajectory["version"] == 2
        assert len(trajectory["events"]) == 4
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
    assert parsed.external_id == (
        "2c139dae-bdef-46f8-b328-b2f54ef450f6#subagent:agent-a9aa01b"
    )
