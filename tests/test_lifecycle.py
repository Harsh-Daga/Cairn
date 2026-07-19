"""Data lifecycle: plan/cleanup, backup/restore, integrity, path safety."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from server.api.action_handlers import (
    DbBackupParams,
    DbCompactParams,
    EmptyParams,
    LifecycleCleanupParams,
    LifecyclePlanParams,
    _db_backup_action,
    _db_compact_action,
    _db_integrity_action,
    _lifecycle_cleanup_action,
    _lifecycle_plan_action,
)
from server.api.bootstrap import bootstrap_runtime
from server.api.context import ActionCtx
from server.config import Settings
from server.store.lifecycle import (
    _assert_under_cairn,
    backup_database,
    db_path,
    list_database_backups,
    plan_cleanup,
    restore_database,
    verify_integrity,
)
from server.util.ids import new_ulid
from server.util.private_files import write_private_text


def _ctx(runtime: object) -> ActionCtx:
    return ActionCtx(
        db=runtime.database,  # type: ignore[attr-defined]
        workspace_id=runtime.workspace_id,  # type: ignore[attr-defined]
        workspace_root=runtime.workspace_root,  # type: ignore[attr-defined]
        event_bus=runtime.event_bus,  # type: ignore[attr-defined]
        pipeline=runtime.pipeline,  # type: ignore[attr-defined]
        jobs=runtime.jobs,  # type: ignore[attr-defined]
    )


def _seed_old_trace(runtime: object, *, text: str = "secret prompt") -> tuple[str, str]:
    ws_id = runtime.workspace_id  # type: ignore[attr-defined]
    trace_id = new_ulid()
    span_id = new_ulid()
    old = (datetime.now(UTC) - timedelta(days=120)).isoformat()

    def _write(conn: sqlite3.Connection) -> None:
        conn.execute(
            "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
            "input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
            "VALUES (?, ?, 'cursor', ?, 'completed', 'old', 1, 1, 0.0, 'priced', 1, 0)",
            (trace_id, ws_id, old),
        )
        conn.execute(
            "INSERT INTO spans (span_id, trace_id, seq, kind, status, text_inline, text_hash) "
            "VALUES (?, ?, 1, 'user_msg', 'ok', ?, 'hash-keep')",
            (span_id, trace_id, text),
        )

    runtime.database.write(_write)  # type: ignore[attr-defined]
    return trace_id, span_id


def _runtime(tmp_path: Path, *, toml: str = "") -> object:
    settings = Settings(workspace_root=tmp_path / "ws")
    settings.workspace_root.mkdir()
    (settings.workspace_root / ".cairn").mkdir()
    if toml:
        write_private_text(settings.workspace_root / ".cairn" / "config.toml", toml)
    return bootstrap_runtime(settings)


def _shutdown(runtime: object) -> None:
    runtime.jobs.shutdown(wait=False)  # type: ignore[attr-defined]
    runtime.pipeline.stop()  # type: ignore[attr-defined]
    runtime.database.close()  # type: ignore[attr-defined]


def test_plan_is_dry_run(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    _seed_old_trace(runtime)
    plan = plan_cleanup(
        runtime.database.reader,  # type: ignore[attr-defined]
        workspace_id=runtime.workspace_id,  # type: ignore[attr-defined]
        mode="strip_text",
        retain_days=90,
    )
    assert plan.dry_run is True
    assert plan.traces_matched == 1
    assert plan.spans_with_text == 1
    assert plan.source_logs_untouched is True
    _shutdown(runtime)


def test_strip_requires_confirm_and_keeps_hash(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    _trace_id, span_id = _seed_old_trace(runtime)
    ctx = _ctx(runtime)
    blocked = _lifecycle_cleanup_action(
        LifecycleCleanupParams(mode="strip_text", retain_days=90, confirm=False),
        ctx,
    )
    assert blocked["ok"] is False
    assert blocked["error"] == "confirmation_required"

    ok = _lifecycle_cleanup_action(
        LifecycleCleanupParams(mode="strip_text", retain_days=90, confirm=True),
        ctx,
    )
    assert ok["ok"] is True
    assert ok["stripped"] == 1
    row = runtime.database.reader.execute(  # type: ignore[attr-defined]
        "SELECT text_inline, text_hash FROM spans WHERE span_id = ?",
        (span_id,),
    ).fetchone()
    assert row["text_inline"] is None
    assert row["text_hash"] == "hash-keep"
    _shutdown(runtime)


def test_delete_traces_warn_only_by_default(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    _seed_old_trace(runtime)
    ctx = _ctx(runtime)
    result = _lifecycle_cleanup_action(
        LifecycleCleanupParams(mode="delete_traces", retain_days=90, confirm=True),
        ctx,
    )
    assert result["ok"] is False
    assert result["error"] == "destructive_disabled"
    count = runtime.database.reader.execute(  # type: ignore[attr-defined]
        "SELECT COUNT(*) AS n FROM traces"
    ).fetchone()
    assert int(count["n"]) == 1
    _shutdown(runtime)


def test_delete_traces_with_destructive_flag(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        toml="[lifecycle]\ndestructive_enabled = true\ndefault_retain_days = 90\n",
    )
    trace_id, _span_id = _seed_old_trace(runtime)
    ctx = _ctx(runtime)
    plan = _lifecycle_plan_action(
        LifecyclePlanParams(mode="delete_traces", retain_days=90),
        ctx,
    )
    assert plan["traces_matched"] == 1
    result = _lifecycle_cleanup_action(
        LifecycleCleanupParams(mode="delete_traces", retain_days=90, confirm=True),
        ctx,
    )
    assert result["ok"] is True
    assert result["deleted_traces"] == 1
    gone = runtime.database.reader.execute(  # type: ignore[attr-defined]
        "SELECT COUNT(*) AS n FROM traces WHERE trace_id = ?",
        (trace_id,),
    ).fetchone()
    assert int(gone["n"]) == 0
    _shutdown(runtime)


def test_backup_restore_and_path_safety(tmp_path: Path) -> None:
    runtime = _runtime(
        tmp_path,
        toml="[lifecycle]\ndestructive_enabled = true\n",
    )
    _seed_old_trace(runtime)
    ctx = _ctx(runtime)
    backed = _db_backup_action(DbBackupParams(label="test"), ctx)
    assert backed["ok"] is True
    backup = Path(backed["path"])
    assert backup.is_file()
    assert ".cairn" in backup.parts

    listed = list_database_backups(ctx.workspace_root)
    assert listed["ok"] is True
    assert listed["count"] >= 1
    assert any(item["path"] == str(backup) for item in listed["backups"])

    preview = restore_database(ctx.workspace_root, backup=backup, dry_run=True)
    assert preview["ok"] is True
    assert preview["dry_run"] is True
    assert preview["would_replace"] == str(db_path(ctx.workspace_root))
    assert preview["destructive_enabled"] is True
    assert verify_integrity(db_path(ctx.workspace_root))["ok"] is True

    with pytest.raises(ValueError, match="outside workspace"):
        _assert_under_cairn(ctx.workspace_root, tmp_path / "evil.db")

    root = ctx.workspace_root
    _shutdown(runtime)

    live = db_path(root)
    live.write_bytes(b"not-a-sqlite-db")
    assert verify_integrity(live)["ok"] is False
    blocked = restore_database(root, backup=backup, confirm=False)
    assert blocked["error"] == "confirmation_required"
    restored = restore_database(root, backup=backup, confirm=True)
    assert restored["ok"] is True
    assert verify_integrity(db_path(root))["ok"] is True


def test_integrity_and_compact(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    ctx = _ctx(runtime)
    integrity = _db_integrity_action(EmptyParams(), ctx)
    assert integrity["ok"] is True
    blocked = _db_compact_action(DbCompactParams(confirm=False), ctx)
    assert blocked["error"] == "confirmation_required"
    compacted = _db_compact_action(DbCompactParams(confirm=True), ctx)
    assert compacted["ok"] is True
    _shutdown(runtime)


def test_backup_helper_creates_private_dir(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    cairn = root / ".cairn"
    cairn.mkdir()
    db = cairn / "cairn.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE t (id INTEGER)")
    conn.commit()
    conn.close()
    result = backup_database(root, label="unit")
    assert result["ok"] is True
    assert Path(result["path"]).is_file()
