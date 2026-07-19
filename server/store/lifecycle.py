"""Workspace data lifecycle: plan/cleanup, backup/restore, integrity, compact."""

from __future__ import annotations

import shutil
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from server.configuration import load_config
from server.ingest.storage import strip_inline_content
from server.util.private_files import ensure_private_dir
from server.util.resources import inventory_disk

CleanupMode = Literal["strip_text", "delete_traces"]


@dataclass(frozen=True, slots=True)
class CleanupPlan:
    mode: CleanupMode
    dry_run: bool
    traces_matched: int
    spans_with_text: int
    oldest_started_at: str | None
    newest_started_at: str | None
    retain_days: int | None
    source_logs_untouched: bool
    limitation: str


def cairn_dir(workspace_root: Path) -> Path:
    return (workspace_root / ".cairn").resolve()


def db_path(workspace_root: Path) -> Path:
    return cairn_dir(workspace_root) / "cairn.db"


def backups_dir(workspace_root: Path) -> Path:
    return cairn_dir(workspace_root) / "backups" / "manual"


def _assert_under_cairn(workspace_root: Path, path: Path) -> Path:
    """Refuse path traversal / wrong-workspace writes."""
    root = cairn_dir(workspace_root)
    resolved = path.expanduser().resolve()
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"Refusing path outside workspace .cairn/: {resolved}")
    if resolved.is_symlink():
        raise ValueError(f"Refusing symlink path: {resolved}")
    return resolved


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def _table_has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    cols = {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    return column in cols


def plan_cleanup(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    mode: CleanupMode = "strip_text",
    retain_days: int | None = None,
) -> CleanupPlan:
    """Count what a cleanup would affect (never mutates)."""
    params: list[Any] = [workspace_id]
    age_sql = ""
    if retain_days is not None and retain_days > 0:
        cutoff = (datetime.now(UTC) - timedelta(days=retain_days)).isoformat()
        age_sql = " AND t.started_at < ?"
        params.append(cutoff)
    row = conn.execute(
        f"""
        SELECT COUNT(DISTINCT t.trace_id) AS traces,
               COUNT(CASE WHEN s.text_inline IS NOT NULL AND s.text_inline != ''
                          THEN 1 END) AS with_text,
               MIN(t.started_at) AS oldest,
               MAX(t.started_at) AS newest
        FROM traces t
        LEFT JOIN spans s ON s.trace_id = t.trace_id
        WHERE t.workspace_id = ?{age_sql}
        """,
        params,
    ).fetchone()
    traces = int(row["traces"] or 0) if row else 0
    with_text = int(row["with_text"] or 0) if row else 0
    return CleanupPlan(
        mode=mode,
        dry_run=True,
        traces_matched=traces,
        spans_with_text=with_text,
        oldest_started_at=str(row["oldest"]) if row and row["oldest"] else None,
        newest_started_at=str(row["newest"]) if row and row["newest"] else None,
        retain_days=retain_days,
        source_logs_untouched=True,
        limitation=(
            "Cleanup never deletes agent source logs. "
            "strip_text nulls text_inline only; delete_traces removes Cairn copies "
            "and requires confirm=true when destructive retention is enabled."
        ),
    )


def _resolve_retain_days(workspace_root: Path, retain_days: int | None) -> int | None:
    """None/omitted → config default; 0 → no age filter (all matching rows)."""
    if retain_days is None:
        return load_config(workspace_root).lifecycle.default_retain_days
    if retain_days <= 0:
        return None
    return retain_days


def run_cleanup(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    workspace_root: Path,
    mode: CleanupMode = "strip_text",
    retain_days: int | None = None,
    confirm: bool = False,
    limit: int = 5_000,
) -> dict[str, Any]:
    """Execute cleanup after confirmation. Default path is strip_text."""
    lifecycle = load_config(workspace_root).lifecycle
    days = _resolve_retain_days(workspace_root, retain_days)
    plan = plan_cleanup(conn, workspace_id=workspace_id, mode=mode, retain_days=days)
    if mode == "delete_traces":
        if not lifecycle.destructive_enabled:
            return {
                "ok": False,
                "error": "destructive_disabled",
                "message": (
                    "Set [lifecycle].destructive_enabled = true before deleting traces. "
                    "Default is warn-only."
                ),
                "plan": asdict(plan),
            }
        if not confirm:
            return {
                "ok": False,
                "error": "confirmation_required",
                "message": "Pass confirm=true after reviewing dry-run counts.",
                "plan": asdict(plan),
            }
        return _delete_traces(
            conn,
            workspace_id=workspace_id,
            retain_days=days,
            limit=limit,
            plan=plan,
        )
    if not confirm and plan.spans_with_text > 0:
        return {
            "ok": False,
            "error": "confirmation_required",
            "message": "Pass confirm=true (or use lifecycle_plan) before stripping text.",
            "plan": asdict(plan),
        }
    # Age window → balanced strip; no age filter → metrics (all text_inline).
    strip_mode: Literal["metrics", "balanced"] = "balanced" if days is not None else "metrics"
    result = strip_inline_content(
        conn,
        workspace_id=workspace_id,
        mode=strip_mode,
        retain_days=days,
        limit=limit,
    )
    return {
        "ok": True,
        "mode": "strip_text",
        "source_logs_untouched": True,
        **result,
        "plan": asdict(plan),
    }


def _delete_traces(
    conn: sqlite3.Connection,
    *,
    workspace_id: str,
    retain_days: int | None,
    limit: int,
    plan: CleanupPlan,
) -> dict[str, Any]:
    params: list[Any] = [workspace_id]
    age_sql = ""
    if retain_days is not None and retain_days > 0:
        cutoff = (datetime.now(UTC) - timedelta(days=retain_days)).isoformat()
        age_sql = " AND started_at < ?"
        params.append(cutoff)
    params.append(max(1, min(int(limit), 50_000)))
    ids = [
        str(row["trace_id"])
        for row in conn.execute(
            f"""
            SELECT trace_id FROM traces
            WHERE workspace_id = ?{age_sql}
            ORDER BY started_at ASC
            LIMIT ?
            """,
            params,
        ).fetchall()
    ]
    deleted = 0
    for trace_id in ids:
        if _table_exists(conn, "span_links"):
            conn.execute(
                """
                DELETE FROM span_links WHERE from_span_id IN (
                  SELECT span_id FROM spans WHERE trace_id = ?
                ) OR to_span_id IN (
                  SELECT span_id FROM spans WHERE trace_id = ?
                )
                """,
                (trace_id, trace_id),
            )
        if _table_exists(conn, "context_regions"):
            conn.execute(
                """
                DELETE FROM context_regions WHERE span_id IN (
                  SELECT span_id FROM spans WHERE trace_id = ?
                )
                """,
                (trace_id,),
            )
        for table in (
            "mcp_consultations",
            "correction_relabels",
            "spans",
            "outcomes",
            "diagnostics",
            "data_quality",
            "fingerprints",
            "verification_receipts",
            "session_corrections",
        ):
            if _table_has_column(conn, table, "trace_id"):
                conn.execute(f"DELETE FROM {table} WHERE trace_id = ?", (trace_id,))
        conn.execute("DELETE FROM traces WHERE trace_id = ?", (trace_id,))
        deleted += 1
    return {
        "ok": True,
        "mode": "delete_traces",
        "deleted_traces": deleted,
        "source_logs_untouched": True,
        "plan": asdict(plan),
        "limitation": "Resumable — re-run until dry-run traces_matched is 0 for the age window.",
    }


def verify_integrity(db_file: Path) -> dict[str, Any]:
    if not db_file.is_file():
        return {"ok": True, "detail": "no database yet", "path": str(db_file)}
    try:
        conn = sqlite3.connect(f"file:{db_file.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        quick = conn.execute("PRAGMA quick_check").fetchone()
        fk = conn.execute("SELECT * FROM pragma_foreign_key_check LIMIT 5").fetchall()
        conn.close()
    except sqlite3.DatabaseError as exc:
        return {"ok": False, "detail": str(exc), "path": str(db_file)}
    quick_ok = quick is not None and str(quick[0]).lower() == "ok"
    ok = quick_ok and not fk
    detail = (
        "quick_check: ok; foreign_key_check: ok"
        if ok
        else f"quick_check: {quick[0] if quick else 'n/a'}; fk_issues: {len(fk)}"
    )
    return {"ok": ok, "detail": detail, "path": str(db_file)}


def backup_database(workspace_root: Path, *, label: str | None = None) -> dict[str, Any]:
    source = db_path(workspace_root)
    if not source.is_file():
        return {"ok": False, "error": "no_database", "message": "No cairn.db to back up."}
    out_dir = backups_dir(workspace_root)
    ensure_private_dir(out_dir)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"-{label}" if label else ""
    dest = out_dir / f"cairn-{stamp}{suffix}.db"
    src_conn = sqlite3.connect(str(source))
    try:
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()
    return {
        "ok": True,
        "path": str(dest),
        "bytes": dest.stat().st_size,
        "source_logs_untouched": True,
    }


def restore_database(
    workspace_root: Path,
    *,
    backup: Path,
    confirm: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    dest = db_path(workspace_root)
    ensure_private_dir(dest.parent)
    source = _assert_under_cairn(workspace_root, backup)
    if not source.is_file():
        raise ValueError(f"Backup not found: {source}")
    backup_integrity = verify_integrity(source)
    live_integrity = (
        verify_integrity(dest) if dest.is_file() else {"ok": False, "error": "no_live_db"}
    )
    would_pre_restore = bool(dest.is_file() and live_integrity.get("ok"))
    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "backup": str(source),
            "backup_bytes": source.stat().st_size,
            "would_replace": str(dest),
            "live_bytes": dest.stat().st_size if dest.is_file() else 0,
            "would_create_pre_restore_backup": would_pre_restore,
            "backup_integrity": backup_integrity,
            "live_integrity": live_integrity,
            "destructive_enabled": load_config(workspace_root).lifecycle.destructive_enabled,
            "source_logs_untouched": True,
            "limitation": "Dry-run only; no files were modified.",
        }
    if not confirm:
        return {
            "ok": False,
            "error": "confirmation_required",
            "message": "Pass confirm=true to replace cairn.db from a backup.",
        }
    lifecycle = load_config(workspace_root).lifecycle
    if not lifecycle.destructive_enabled:
        return {
            "ok": False,
            "error": "destructive_disabled",
            "message": "Set [lifecycle].destructive_enabled = true before restore.",
        }
    safety: dict[str, Any] = {"path": None}
    if would_pre_restore:
        safety = backup_database(workspace_root, label="pre-restore")
    shutil.copy2(source, dest)
    integrity = verify_integrity(dest)
    return {
        "ok": bool(integrity["ok"]),
        "restored_from": str(source),
        "path": str(dest),
        "pre_restore_backup": safety.get("path"),
        "integrity": integrity,
        "source_logs_untouched": True,
    }


def list_database_backups(workspace_root: Path) -> dict[str, Any]:
    out_dir = backups_dir(workspace_root)
    items: list[dict[str, Any]] = []
    if out_dir.is_dir():
        for path in sorted(out_dir.glob("*.db"), reverse=True):
            if path.is_symlink() or not path.is_file():
                continue
            items.append(
                {
                    "path": str(path),
                    "name": path.name,
                    "bytes": path.stat().st_size,
                    "mtime": datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
                    .replace(microsecond=0)
                    .isoformat()
                    .replace("+00:00", "Z"),
                }
            )
    return {
        "ok": True,
        "backups_dir": str(out_dir),
        "count": len(items),
        "backups": items[:50],
        "limitation": "Lists files under .cairn/backups/manual only (newest 50).",
    }


def compact_database(workspace_root: Path, *, confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        return {
            "ok": False,
            "error": "confirmation_required",
            "message": "Pass confirm=true to checkpoint WAL and VACUUM.",
        }
    path = db_path(workspace_root)
    if not path.is_file():
        return {"ok": False, "error": "no_database", "message": "No cairn.db to compact."}
    before = path.stat().st_size
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("VACUUM")
        conn.commit()
    finally:
        conn.close()
    after = path.stat().st_size
    return {
        "ok": True,
        "path": str(path),
        "bytes_before": before,
        "bytes_after": after,
        "source_logs_untouched": True,
        "limitation": "VACUUM rewrites the DB file; take a backup first for large workspaces.",
    }


def lifecycle_status(workspace_root: Path) -> dict[str, Any]:
    config = load_config(workspace_root).lifecycle
    disk = inventory_disk(workspace_root)
    integrity = verify_integrity(db_path(workspace_root))
    return {
        "destructive_enabled": config.destructive_enabled,
        "default_retain_days": config.default_retain_days,
        "warn_only_default": not config.destructive_enabled,
        "disk": {
            "total_bytes": disk["total_bytes"],
            "cairn_dir": disk["cairn_dir"],
        },
        "integrity": integrity,
        "backups_dir": str(backups_dir(workspace_root)),
        "limitation": (
            "Warn-only until [lifecycle].destructive_enabled is set. "
            "Source agent logs are never modified by Cairn cleanup."
        ),
    }
