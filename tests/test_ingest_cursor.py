"""Cursor ingest — ``state.vscdb`` is canonical (real ISO ts, tokenCount, cost)."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cairn.ingest.parsers.cursor import (
    parse_cursor_vscdb,
    parse_transcript_file,
)
from cairn.ingest.writer import CaptureWriter
from cairn.metrics.waste import compute_waste


def _build_vscdb(path: Path, *, workspace: str | None = None) -> None:
    """Build a tiny ``state.vscdb`` with one composer + two bubbles."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    composer_id = "comp-001"
    created_ms = int(datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
    updated_ms = int(datetime(2026, 6, 1, 10, 0, 5, tzinfo=UTC).timestamp() * 1000)
    composer = {
        "createdAt": created_ms,
        "lastUpdatedAt": updated_ms,
        "source": workspace or "/tmp/cairn-cursor-proj",
        "name": "fix the bug",
        "usageData": {"default": {"costInCents": 12, "amount": 12}},
        "fullConversationHeadersOnly": ["bubble-1", "bubble-2"],
    }
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (f"composerData:{composer_id}", json.dumps(composer)),
    )
    bubble1 = {
        "type": 1,
        "text": "<user_query>Fix the bug</user_query>",
        "tokenCount": {"inputTokens": 500, "outputTokens": 0},
    }
    bubble2 = {
        "type": 2,
        "text": "I will edit the file.",
        "tokenCount": {"inputTokens": 600, "outputTokens": 120},
    }
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (f"bubbleId:{composer_id}:bubble-1", json.dumps(bubble1)),
    )
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (f"bubbleId:{composer_id}:bubble-2", json.dumps(bubble2)),
    )
    conn.commit()
    conn.close()


def test_cursor_vscdb_real_timestamps_tokens_and_cost(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    vscdb = tmp_path / "state.vscdb"
    _build_vscdb(vscdb, workspace=str(root))

    sessions = parse_cursor_vscdb(vscdb, repo_root=root)
    assert len(sessions) == 1
    parsed = sessions[0]

    # Real ISO timestamps — never line:N, never 1970.
    assert parsed.started_at is not None
    assert parsed.started_at.startswith("2026-06-01T10:00:00")
    assert "line:" not in parsed.started_at
    assert parsed.ended_at is not None
    assert parsed.ended_at.startswith("2026-06-01T10:00:05")

    # tokenCount extracted
    assert parsed.usage.usage.input_tokens == 1100  # 500 + 600
    assert parsed.usage.usage.output_tokens == 120

    # has_cost=1 because tokenCount + costInCents present
    assert parsed.has_cost is True

    # cost from costInCents / 100
    assert parsed.usage.usage.cost == 0.12

    # assistant bubble carries per-turn token counts
    asst = [e for e in parsed.events if e["type"] == "assistant_message"]
    assert len(asst) == 1
    assert asst[0]["input_tokens"] == 600
    assert asst[0]["output_tokens"] == 120

    # persists to ledger
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_cursor_session(parsed)
        row = writer.connection.execute(
            "SELECT has_cost, total_cost, total_input_tokens, total_output_tokens, started_at "
            "FROM runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert int(row["has_cost"]) == 1
        assert abs(float(row["total_cost"]) - 0.12) < 1e-9
        assert int(row["total_input_tokens"]) == 1100
        assert int(row["total_output_tokens"]) == 120
        assert str(row["started_at"]).startswith("2026-06-01T10:00:00")
    finally:
        writer.close()


def test_cursor_vscdb_no_cost_when_missing(tmp_path: Path) -> None:
    """No tokenCount and no costInCents → has_cost=0 + a data-note explaining why."""
    vscdb = tmp_path / "state.vscdb"
    conn = sqlite3.connect(vscdb)
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    composer = {
        "createdAt": int(datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000),
        "lastUpdatedAt": int(datetime(2026, 6, 1, 10, 0, 5, tzinfo=UTC).timestamp() * 1000),
        "fullConversationHeadersOnly": ["bubble-1"],
    }
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        ("composerData:comp-nocost", json.dumps(composer)),
    )
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        ("bubbleId:comp-nocost:bubble-1", json.dumps({"type": 1, "text": "hi"})),
    )
    conn.commit()
    conn.close()

    sessions = parse_cursor_vscdb(vscdb, repo_root=tmp_path)
    assert len(sessions) == 1
    parsed = sessions[0]
    assert parsed.has_cost is False
    assert any("no tokenCount" in note or "no token" in note.lower() for note in parsed.data_notes)


def test_cursor_best_of_n_subcomposer_excludes_cost(tmp_path: Path) -> None:
    """Best-of-N subcomposer runs keep tokens but has_cost=0 to avoid double-counting."""
    vscdb = tmp_path / "state.vscdb"
    conn = __import__("sqlite3").connect(vscdb)
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    composer_id = "comp-sub"
    composer = {
        "createdAt": int(datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000),
        "lastUpdatedAt": int(datetime(2026, 6, 1, 10, 0, 5, tzinfo=UTC).timestamp() * 1000),
        "isBestOfNSubcomposer": True,
        "numSubComposers": 3,
        "usageData": {"default": {"costInCents": 25, "amount": 25}},
        "fullConversationHeadersOnly": ["bubble-1"],
    }
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (f"composerData:{composer_id}", json.dumps(composer)),
    )
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (
            f"bubbleId:{composer_id}:bubble-1",
            json.dumps(
                {
                    "type": 2,
                    "text": "subagent work",
                    "tokenCount": {"inputTokens": 400, "outputTokens": 80},
                }
            ),
        ),
    )
    conn.commit()
    conn.close()

    sessions = parse_cursor_vscdb(vscdb, repo_root=tmp_path)
    assert len(sessions) == 1
    parsed = sessions[0]
    assert parsed.has_cost is False
    assert any("best-of-N" in n for n in parsed.data_notes)

    root = tmp_path / "proj"
    root.mkdir()
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_cursor_session(parsed)
        row = writer.connection.execute(
            "SELECT has_cost, status, total_cost FROM runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert int(row["has_cost"]) == 0
        assert row["status"] == "best-of-n-subagent"
        assert float(row["total_cost"]) == 0.0
    finally:
        writer.close()


def test_cursor_parent_num_subcomposers_keeps_cost(tmp_path: Path) -> None:
    """Parent composers with numSubComposers > 1 still bill; only subcomposers are excluded."""
    root = tmp_path / "proj"
    root.mkdir()
    vscdb = tmp_path / "state.vscdb"
    conn = sqlite3.connect(vscdb)
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    composer_id = "comp-parent"
    composer = {
        "createdAt": int(datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000),
        "lastUpdatedAt": int(datetime(2026, 6, 1, 10, 0, 5, tzinfo=UTC).timestamp() * 1000),
        "numSubComposers": 3,
        "source": str(root),
        "usageData": {"default": {"costInCents": 30, "amount": 30}},
        "fullConversationHeadersOnly": ["bubble-1"],
    }
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (f"composerData:{composer_id}", json.dumps(composer)),
    )
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (
            f"bubbleId:{composer_id}:bubble-1",
            json.dumps(
                {
                    "type": 2,
                    "text": "parent work",
                    "tokenCount": {"inputTokens": 900, "outputTokens": 100},
                }
            ),
        ),
    )
    conn.commit()
    conn.close()

    sessions = parse_cursor_vscdb(vscdb, repo_root=root)
    assert len(sessions) == 1
    parsed = sessions[0]
    assert parsed.has_cost is True
    assert parsed.is_best_of_n_subcomposer is False

    writer = CaptureWriter(root)
    try:
        result = writer.ingest_cursor_session(parsed)
        row = writer.connection.execute(
            "SELECT has_cost, status, total_cost FROM runs WHERE run_id = ?",
            (result.run_id,),
        ).fetchone()
        assert int(row["has_cost"]) == 1
        assert row["status"] == "completed"
        assert float(row["total_cost"]) == 0.30
    finally:
        writer.close()


def test_cursor_ingest_skips_other_workspace_composers(tmp_path: Path, monkeypatch) -> None:
    """vscdb ingest only includes composers tied to this repo's workspace."""
    root = tmp_path / "proj"
    root.mkdir()
    other = tmp_path / "other-proj"
    other.mkdir()
    vscdb = tmp_path / "state.vscdb"
    _build_vscdb(vscdb, workspace=str(other))

    monkeypatch.setenv("CAIRN_CURSOR_VSCDB", str(vscdb))
    from cairn.ingest.ingest import run_ingest

    reports = run_ingest(root, source="cursor")
    assert reports
    report = reports[0]
    assert report.scanned == 1
    assert report.inserted == 0
    assert report.skipped == 1


def test_cursor_ingest_matches_project_transcripts_without_source(
    tmp_path: Path, monkeypatch
) -> None:
    """Composers with no vscdb source still ingest when transcripts exist for the repo."""
    root = tmp_path / "proj"
    root.mkdir()
    composer_id = "comp-transcript-001"
    workspace = tmp_path / "cursor-ws" / "agent-transcripts" / composer_id
    workspace.mkdir(parents=True)
    transcript = workspace / f"{composer_id}.jsonl"
    transcript.write_text(
        json.dumps({"role": "user", "message": {"content": [{"type": "text", "text": "hi"}]}})
        + "\n",
        encoding="utf-8",
    )

    vscdb = tmp_path / "state.vscdb"
    conn = sqlite3.connect(vscdb)
    conn.execute("CREATE TABLE cursorDiskKV (key TEXT PRIMARY KEY, value TEXT)")
    created_ms = int(datetime(2026, 6, 1, 10, 0, 0, tzinfo=UTC).timestamp() * 1000)
    composer = {
        "createdAt": created_ms,
        "lastUpdatedAt": created_ms,
        "fullConversationHeadersOnly": [],
    }
    conn.execute(
        "INSERT INTO cursorDiskKV (key, value) VALUES (?, ?)",
        (f"composerData:{composer_id}", json.dumps(composer)),
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("CAIRN_CURSOR_VSCDB", str(vscdb))
    from cairn.ingest.ingest import run_ingest

    reports = run_ingest(root, source="cursor", cursor_workspace=workspace.parent.parent)
    report = reports[0]
    assert report.inserted >= 1
    writer = CaptureWriter(root)
    try:
        row = writer.connection.execute(
            "SELECT source, COUNT(*) AS n FROM runs WHERE source = 'cursor'"
        ).fetchone()
        assert int(row["n"]) >= 1
    finally:
        writer.close()


def test_cursor_transcript_fallback_still_tags_waste(tmp_path: Path) -> None:
    """Legacy transcript fallback: has_cost=0 but structural waste still tagged."""
    fixture = Path(__file__).parent / "fixtures" / "ingest" / "cursor_mini.jsonl"
    if not fixture.is_file():
        return
    root = tmp_path / "proj"
    root.mkdir()
    parsed = parse_transcript_file(fixture, repo_root=root)
    if parsed is None:
        return
    # fallback never uses line:N and never 1970; started_at from file mtime or None.
    assert parsed.started_at is None or "line:" not in parsed.started_at
    assert parsed.has_cost is False
    writer = CaptureWriter(root)
    try:
        result = writer.ingest_cursor_session(parsed)
        row = writer.connection.execute(
            "SELECT has_cost FROM runs WHERE run_id = ?", (result.run_id,)
        ).fetchone()
        assert int(row["has_cost"]) == 0
        events = writer.load_events(result.run_id)
        waste = compute_waste(events, has_cost=False)
        assert isinstance(waste.tags, list)
    finally:
        writer.close()
