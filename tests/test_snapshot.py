"""Phase 15 snapshot and session diff tests."""

from __future__ import annotations

from pathlib import Path

from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from cairn.snapshot.engine import (
    create_snapshot,
    diff_sessions,
    diff_snapshots,
    list_snapshots,
    restore_snapshot,
    snapshots_dir,
)
from cairn.snapshot.protocol import SNAPSHOT_VERSION
from tests.test_capture_phase5 import CLAUDE_FIXTURE


def _ingest(repo: Path) -> str:
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()
    return parsed.external_id


def test_create_and_list_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    session_id = _ingest(repo)
    manifest = create_snapshot(repo, label="baseline")
    assert manifest.cairn_snapshot_version == SNAPSHOT_VERSION
    assert session_id in manifest.sessions
    snap_path = snapshots_dir(repo) / manifest.snapshot_id
    assert (snap_path / "ledger.db").is_file()
    assert (snap_path / "manifest.json").is_file()
    listed = list_snapshots(repo)
    assert len(listed) == 1
    assert listed[0].snapshot_id == manifest.snapshot_id


def test_restore_snapshot(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    session_id = _ingest(repo)
    manifest = create_snapshot(repo)

    writer = CaptureWriter(repo)
    try:
        writer.connection.execute("DELETE FROM events")
        writer.connection.execute("DELETE FROM runs")
        writer.connection.commit()
        assert writer.load_session_by_external_id(session_id) is None
    finally:
        writer.close()

    restored = restore_snapshot(repo, manifest.snapshot_id)
    assert restored.snapshot_id == manifest.snapshot_id
    writer = CaptureWriter(repo)
    try:
        summary = writer.load_session_by_external_id(session_id)
        assert summary is not None
        assert summary.event_count == 4
    finally:
        writer.close()


def test_diff_snapshots_and_sessions(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    session_id = _ingest(repo)
    first = create_snapshot(repo, label="v1")
    second = create_snapshot(repo, label="v2")
    snap_diff = diff_snapshots(repo, first.snapshot_id, second.snapshot_id)
    assert snap_diff["sessions_added"] == []
    assert snap_diff["sessions_removed"] == []

    session_diff = diff_sessions(repo, session_id, session_id)
    assert session_diff["event_count_a"] == session_diff["event_count_b"]
    assert session_diff["shared_tools"]
