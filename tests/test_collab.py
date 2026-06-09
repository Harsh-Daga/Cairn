"""Phase 14 collaboration sync tests."""

from __future__ import annotations

import json
from pathlib import Path

from cairn.collab.cursor import load_cursor
from cairn.collab.export import export_sync_bundle
from cairn.collab.import_bundle import import_sync_bundle
from cairn.collab.protocol import SYNC_VERSION
from cairn.ingest.parsers.claude_code import parse_jsonl_file
from cairn.ingest.writer import CaptureWriter
from tests.test_capture_phase5 import CLAUDE_FIXTURE


def _ingest_fixture(repo: Path) -> str:
    parsed = parse_jsonl_file(CLAUDE_FIXTURE, repo_root=repo)
    assert parsed is not None
    writer = CaptureWriter(repo)
    try:
        writer.ingest_claude_session(parsed)
    finally:
        writer.close()
    return parsed.external_id


def test_export_sync_bundle(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    session_id = _ingest_fixture(repo)
    bundle_dir = tmp_path / "sync-out"
    manifest = export_sync_bundle(repo, bundle_dir, project_label="demo")
    assert manifest.cairn_sync_version == SYNC_VERSION
    assert session_id in manifest.sessions
    assert (bundle_dir / "manifest.json").is_file()
    assert (bundle_dir / "ledger.db").is_file()
    assert (bundle_dir / "sessions" / f"{session_id}.json").is_file()
    cursor = load_cursor(repo)
    assert cursor.last_sync_at is not None
    assert cursor.session_count == 1


def test_import_sync_bundle_merges_sessions(tmp_path: Path) -> None:
    source_repo = tmp_path / "source"
    source_repo.mkdir()
    session_id = _ingest_fixture(source_repo)
    bundle_dir = tmp_path / "bundle"
    export_sync_bundle(source_repo, bundle_dir)

    target_repo = tmp_path / "target"
    target_repo.mkdir()
    result = import_sync_bundle(target_repo, bundle_dir)
    assert result.runs_inserted >= 1
    assert (target_repo / ".cairn" / "sessions" / f"{session_id}.json").is_file()

    writer = CaptureWriter(target_repo)
    try:
        summary = writer.load_session_by_external_id(session_id)
        assert summary is not None
        assert summary.event_count == 4
    finally:
        writer.close()


def test_import_skips_duplicate_sessions(tmp_path: Path) -> None:
    repo = tmp_path / "proj"
    repo.mkdir()
    session_id = _ingest_fixture(repo)
    bundle_dir = tmp_path / "bundle"
    export_sync_bundle(repo, bundle_dir)

    first = import_sync_bundle(repo, bundle_dir)
    second = import_sync_bundle(repo, bundle_dir)
    assert first.runs_inserted == 0
    assert first.sessions_imported == 0
    assert second.runs_inserted == 0
    assert second.events_inserted == 0

    manifest = json.loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    assert session_id in manifest["sessions"]
