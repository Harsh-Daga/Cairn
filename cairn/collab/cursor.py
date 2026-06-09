"""Local sync cursor persisted under .cairn/sync/."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cairn.collab.protocol import SyncCursor


def sync_dir(project_root: Path) -> Path:
    path = project_root / ".cairn" / "sync"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cursor_path(project_root: Path) -> Path:
    return sync_dir(project_root) / "cursor.json"


def load_cursor(project_root: Path) -> SyncCursor:
    path = cursor_path(project_root)
    if not path.is_file():
        return SyncCursor(last_sync_at=None, last_exported_run_id=None, session_count=0)
    data = json.loads(path.read_text(encoding="utf-8"))
    return SyncCursor(
        last_sync_at=data.get("last_sync_at"),
        last_exported_run_id=data.get("last_exported_run_id"),
        session_count=int(data.get("session_count", 0)),
    )


def save_cursor(project_root: Path, cursor: SyncCursor) -> None:
    path = cursor_path(project_root)
    path.write_text(
        json.dumps(cursor.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def update_cursor(project_root: Path, **fields: Any) -> SyncCursor:
    current = load_cursor(project_root)
    merged = SyncCursor(
        last_sync_at=fields.get("last_sync_at", current.last_sync_at),
        last_exported_run_id=fields.get("last_exported_run_id", current.last_exported_run_id),
        session_count=int(fields.get("session_count", current.session_count)),
    )
    save_cursor(project_root, merged)
    return merged
