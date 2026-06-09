"""Import a file-based sync bundle into a local project."""

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cairn.collab.acl import verify_access_token
from cairn.collab.cursor import update_cursor
from cairn.collab.protocol import SYNC_VERSION, SyncCursor, SyncManifest
from cairn.ingest.project_paths import resolve_git_root
from cairn.ledger.schema import migrate


class ImportResult:
    def __init__(
        self,
        *,
        sessions_imported: int,
        runs_inserted: int,
        events_inserted: int,
    ) -> None:
        self.sessions_imported = sessions_imported
        self.runs_inserted = runs_inserted
        self.events_inserted = events_inserted


def import_sync_bundle(
    project_root: Path,
    source: Path,
    *,
    access_token: str | None = None,
) -> ImportResult:
    """Merge capture sessions from a sync bundle (append-only, no action_cache changes)."""
    root = resolve_git_root(project_root) or project_root.resolve()
    source = source.resolve()
    manifest_path = source / "manifest.json"
    remote_ledger = source / "ledger.db"
    if not manifest_path.is_file() or not remote_ledger.is_file():
        msg = f"invalid sync bundle: {source}"
        raise FileNotFoundError(msg)

    manifest = _load_manifest(manifest_path)
    if not verify_access_token(access_token or "", manifest.access_token_hash):
        msg = "access denied: invalid or missing sync bundle token"
        raise PermissionError(msg)
    if manifest.cairn_sync_version != SYNC_VERSION:
        msg = f"unsupported sync version: {manifest.cairn_sync_version}"
        raise ValueError(msg)

    cairn_dir = root / ".cairn"
    cairn_dir.mkdir(parents=True, exist_ok=True)
    local_ledger = cairn_dir / "ledger.db"
    if not local_ledger.is_file():
        shutil.copy2(remote_ledger, local_ledger)
        sessions_imported = _copy_session_mirrors(source, root)
        update_cursor(
            root,
            last_sync_at=datetime.now(UTC).isoformat(),
            last_exported_run_id=manifest.cursor.last_exported_run_id,
            session_count=manifest.cursor.session_count,
        )
        return ImportResult(
            sessions_imported=sessions_imported,
            runs_inserted=manifest.cursor.session_count,
            events_inserted=0,
        )

    runs_inserted, events_inserted = _merge_capture_ledger(local_ledger, remote_ledger)
    sessions_imported = _copy_session_mirrors(source, root)
    update_cursor(
        root,
        last_sync_at=datetime.now(UTC).isoformat(),
        last_exported_run_id=manifest.cursor.last_exported_run_id,
        session_count=manifest.cursor.session_count,
    )
    return ImportResult(
        sessions_imported=sessions_imported,
        runs_inserted=runs_inserted,
        events_inserted=events_inserted,
    )


def _load_manifest(path: Path) -> SyncManifest:
    data = json.loads(path.read_text(encoding="utf-8"))
    cursor_data = data.get("cursor") or {}
    cursor = SyncCursor(
        last_sync_at=cursor_data.get("last_sync_at"),
        last_exported_run_id=cursor_data.get("last_exported_run_id"),
        session_count=int(cursor_data.get("session_count", 0)),
    )
    token_hash = data.get("access_token_hash")
    return SyncManifest(
        cairn_sync_version=int(data["cairn_sync_version"]),
        exported_at=str(data["exported_at"]),
        project_label=str(data.get("project_label", "")),
        ledger_sha256=str(data.get("ledger_sha256", "")),
        sessions=tuple(str(s) for s in data.get("sessions", [])),
        cursor=cursor,
        access_token_hash=str(token_hash) if token_hash else None,
    )


def _copy_session_mirrors(source: Path, project_root: Path) -> int:
    src = source / "sessions"
    if not src.is_dir():
        return 0
    dest = project_root / ".cairn" / "sessions"
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for mirror in src.glob("*.json"):
        target = dest / mirror.name
        if not target.exists():
            shutil.copy2(mirror, target)
            count += 1
    return count


def _merge_capture_ledger(local_path: Path, remote_path: Path) -> tuple[int, int]:
    local = sqlite3.connect(local_path)
    local.row_factory = sqlite3.Row
    migrate(local)
    remote = sqlite3.connect(remote_path)
    remote.row_factory = sqlite3.Row
    try:
        runs_inserted = 0
        events_inserted = 0
        remote_runs = remote.execute(
            "SELECT * FROM runs WHERE kind = 'capture'"
        ).fetchall()
        for row in remote_runs:
            existing = local.execute(
                "SELECT run_id FROM runs WHERE source = ? AND external_id = ?",
                (row["source"], row["external_id"]),
            ).fetchone()
            if existing is not None:
                continue
            columns = row.keys()
            placeholders = ", ".join("?" for _ in columns)
            col_names = ", ".join(columns)
            local.execute(
                f"INSERT INTO runs ({col_names}) VALUES ({placeholders})",
                tuple(row[c] for c in columns),
            )
            runs_inserted += 1
            run_id = str(row["run_id"])
            for event in remote.execute(
                "SELECT run_id, seq, event_type, payload_json FROM events WHERE run_id = ?",
                (run_id,),
            ):
                local.execute(
                    """
                    INSERT OR IGNORE INTO events (run_id, seq, event_type, payload_json)
                    VALUES (?, ?, ?, ?)
                    """,
                    (event["run_id"], event["seq"], event["event_type"], event["payload_json"]),
                )
                events_inserted += 1
            for artifact in remote.execute(
                "SELECT * FROM file_artifacts WHERE run_id = ?",
                (run_id,),
            ):
                cols = artifact.keys()
                local.execute(
                    f"INSERT OR IGNORE INTO file_artifacts ({', '.join(cols)}) "
                    f"VALUES ({', '.join('?' for _ in cols)})",
                    tuple(artifact[c] for c in cols),
                )
        local.commit()
        return runs_inserted, events_inserted
    finally:
        remote.close()
        local.close()
