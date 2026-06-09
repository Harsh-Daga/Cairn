"""Export a file-based sync bundle for collaboration."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cairn.collab.acl import generate_access_token, hash_access_token
from cairn.collab.cursor import update_cursor
from cairn.collab.protocol import SYNC_VERSION, SyncCursor, SyncManifest
from cairn.ingest.project_paths import resolve_git_root


@dataclass(frozen=True)
class ExportResult:
    manifest: SyncManifest
    access_token: str | None


def export_sync_bundle(
    project_root: Path,
    dest: Path,
    *,
    project_label: str | None = None,
    access_token: str | None = None,
    generate_token: bool = False,
) -> ExportResult:
    """Write a Syncthing-friendly sync directory with ledger snapshot and session mirrors."""
    root = resolve_git_root(project_root) or project_root.resolve()
    ledger = root / ".cairn" / "ledger.db"
    if not ledger.is_file():
        msg = "no ledger found; run capture or build first"
        raise FileNotFoundError(msg)

    dest = dest.resolve()
    if dest.exists() and any(dest.iterdir()):
        msg = f"destination not empty: {dest}"
        raise FileExistsError(msg)

    dest.mkdir(parents=True, exist_ok=True)
    sessions_dest = dest / "sessions"
    sessions_dest.mkdir(parents=True, exist_ok=True)

    shutil.copy2(ledger, dest / "ledger.db")
    ledger_sha256 = _sha256_file(dest / "ledger.db")

    sessions_src = root / ".cairn" / "sessions"
    session_ids: list[str] = []
    if sessions_src.is_dir():
        for mirror in sorted(sessions_src.glob("*.json")):
            shutil.copy2(mirror, sessions_dest / mirror.name)
            session_ids.append(mirror.stem)

    last_run_id = _latest_capture_run_id(ledger)
    exported_at = datetime.now(UTC).isoformat()
    label = project_label or root.name
    cursor = SyncCursor(
        last_sync_at=exported_at,
        last_exported_run_id=last_run_id,
        session_count=len(session_ids),
    )
    token = access_token
    if generate_token and token is None:
        token = generate_access_token()
    token_hash = hash_access_token(token) if token else None
    manifest = SyncManifest(
        cairn_sync_version=SYNC_VERSION,
        exported_at=exported_at,
        project_label=label,
        ledger_sha256=ledger_sha256,
        sessions=tuple(session_ids),
        cursor=cursor,
        access_token_hash=token_hash,
    )
    (dest / "manifest.json").write_text(
        json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    update_cursor(
        root,
        last_sync_at=exported_at,
        last_exported_run_id=last_run_id,
        session_count=len(session_ids),
    )
    return ExportResult(manifest=manifest, access_token=token)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _latest_capture_run_id(ledger_path: Path) -> str | None:
    conn = sqlite3.connect(ledger_path)
    try:
        row = conn.execute(
            """
            SELECT run_id FROM runs
            WHERE kind = 'capture'
            ORDER BY started_at DESC
            LIMIT 1
            """
        ).fetchone()
        return str(row[0]) if row else None
    finally:
        conn.close()
