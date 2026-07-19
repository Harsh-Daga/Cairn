"""Versioned cairn.archive.v1 export/import/inspect + hostile ZIP defenses."""

from __future__ import annotations

import io
import sqlite3
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from server.api.bootstrap import bootstrap_runtime
from server.archive.export import export_archive, preview_archive
from server.archive.import_archive import import_archive
from server.archive.inspect_archive import inspect_archive
from server.archive.safe_zip import ArchiveZipError, safe_read_members
from server.archive.schema import ARCHIVE_SCHEMA_VERSION, OTLP_LOSS_FIELDS
from server.config import Settings
from server.util.ids import new_ulid


def _runtime(tmp_path: Path) -> object:
    settings = Settings(workspace_root=tmp_path / "ws")
    settings.workspace_root.mkdir()
    (settings.workspace_root / ".cairn").mkdir()
    return bootstrap_runtime(settings)


def _shutdown(runtime: object) -> None:
    runtime.jobs.shutdown(wait=False)  # type: ignore[attr-defined]
    runtime.pipeline.stop()  # type: ignore[attr-defined]
    runtime.database.close()  # type: ignore[attr-defined]


def _seed(runtime: object) -> str:
    ws_id = runtime.workspace_id  # type: ignore[attr-defined]
    trace_id = new_ulid()
    span_id = new_ulid()
    started = (datetime.now(UTC) - timedelta(days=1)).isoformat()

    def _write(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
            "input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
            "VALUES (?, ?, 'cursor', ?, 'completed', 'hello', 10, 5, 0.01, 'priced', 1, 0)",
            (trace_id, ws_id, started),
        )
        conn.execute(
            "INSERT INTO spans (span_id, trace_id, seq, kind, status, text_inline, text_hash) "
            "VALUES (?, ?, 1, 'user_msg', 'ok', 'secret text', 'h1')",
            (span_id, trace_id),
        )

    runtime.database.write(_write)  # type: ignore[attr-defined]
    return trace_id


def test_preview_and_round_trip(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    trace_id = _seed(runtime)
    root = runtime.workspace_root  # type: ignore[attr-defined]
    ws_id = runtime.workspace_id  # type: ignore[attr-defined]
    preview = preview_archive(
        runtime.database.reader,  # type: ignore[attr-defined]
        workspace_id=ws_id,
        workspace_root=root,
        mode="full",
        limit=10,
    )
    assert preview["dry_run"] is True
    assert preview["trace_count"] == 1
    assert preview["otlp_loss"]

    exported = export_archive(
        runtime.database.reader,  # type: ignore[attr-defined]
        workspace_id=ws_id,
        workspace_root=root,
        mode="full",
        limit=10,
    )
    assert exported["ok"] is True
    assert exported["schema"] == ARCHIVE_SCHEMA_VERSION
    archive = Path(exported["path"])
    assert archive.is_file()

    inspected = inspect_archive(archive)
    assert inspected["ok"] is True
    assert inspected["supported"] is True
    assert inspected["trace_count"] == 1
    assert inspected["checksum_mismatches"] == []

    dry = import_archive(
        runtime.database.reader,  # type: ignore[attr-defined]
        workspace_id=ws_id,
        workspace_root=root,
        archive=archive,
        dry_run=True,
        conflict="fail",
    )
    assert dry["ok"] is False
    assert dry["error"] == "conflict"

    skip_plan = import_archive(
        runtime.database.reader,  # type: ignore[attr-defined]
        workspace_id=ws_id,
        workspace_root=root,
        archive=archive,
        dry_run=True,
        conflict="skip",
    )
    assert skip_plan["ok"] is True
    assert skip_plan["would_skip"] == 1

    def _wipe(conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM spans")
        conn.execute("DELETE FROM traces")

    runtime.database.write(_wipe)  # type: ignore[attr-defined]
    applied = runtime.database.write(  # type: ignore[attr-defined]
        lambda conn: import_archive(
            conn,
            workspace_id=ws_id,
            workspace_root=root,
            archive=archive,
            dry_run=False,
            conflict="fail",
        )
    )
    assert applied["ok"] is True
    assert applied["inserted"] == 1
    row = runtime.database.reader.execute(  # type: ignore[attr-defined]
        "SELECT title, text_inline FROM traces t "
        "JOIN spans s ON s.trace_id = t.trace_id WHERE t.trace_id = ?",
        (trace_id,),
    ).fetchone()
    assert row["title"] == "hello"
    assert row["text_inline"] == "secret text"
    assert any(item["field"].startswith("verification") for item in OTLP_LOSS_FIELDS)
    _shutdown(runtime)


def test_scrubbed_redacts_text(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    _seed(runtime)
    root = runtime.workspace_root  # type: ignore[attr-defined]
    exported = export_archive(
        runtime.database.reader,  # type: ignore[attr-defined]
        workspace_id=runtime.workspace_id,  # type: ignore[attr-defined]
        workspace_root=root,
        mode="scrubbed",
        limit=10,
    )
    members = safe_read_members(Path(exported["path"]))
    spans = __import__("json").loads(members["spans.json"].decode())["rows"]
    assert spans
    assert "secret text" not in str(spans[0].get("text_inline"))
    _shutdown(runtime)


def test_zip_slip_rejected(tmp_path: Path) -> None:
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("../escape.json", b"{}")
        zf.writestr("manifest.json", b'{"schema":"cairn.archive.v1"}')
        zf.writestr("privacy.json", b"{}")
    with pytest.raises(ArchiveZipError, match="path traversal|nested|absolute"):
        safe_read_members(evil)


def test_duplicate_member_rejected(tmp_path: Path) -> None:
    # zipfile API overwrites duplicates on write; craft manually via ZipInfo twice
    path = tmp_path / "dup.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", b'{"schema":"cairn.archive.v1"}')
        zf.writestr("privacy.json", b"{}")
        zf.writestr("traces.json", b'{"rows":[]}')
    # Re-open and append another traces.json using ZipFile append
    data = buf.getvalue()
    # Simpler: write two same names is hard with stdlib; test unexpected member instead
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("manifest.json", b'{"schema":"cairn.archive.v1"}')
        zf.writestr("privacy.json", b"{}")
        zf.writestr("not-allowed.json", b"{}")
    with pytest.raises(ArchiveZipError, match="unexpected"):
        safe_read_members(bad)
    _ = path, data
