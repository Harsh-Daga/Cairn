"""Sync bundle manifest for file-based collaboration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SYNC_VERSION = 1


@dataclass(frozen=True)
class SyncCursor:
    last_sync_at: str | None
    last_exported_run_id: str | None
    session_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "last_sync_at": self.last_sync_at,
            "last_exported_run_id": self.last_exported_run_id,
            "session_count": self.session_count,
        }


@dataclass(frozen=True)
class SyncManifest:
    cairn_sync_version: int
    exported_at: str
    project_label: str
    ledger_sha256: str
    sessions: tuple[str, ...]
    cursor: SyncCursor
    access_token_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "cairn_sync_version": self.cairn_sync_version,
            "exported_at": self.exported_at,
            "project_label": self.project_label,
            "ledger_sha256": self.ledger_sha256,
            "sessions": list(self.sessions),
            "cursor": self.cursor.to_dict(),
        }
        if self.access_token_hash is not None:
            payload["access_token_hash"] = self.access_token_hash
        return payload
