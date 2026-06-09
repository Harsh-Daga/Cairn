"""Snapshot manifest format."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

SNAPSHOT_VERSION = 1


@dataclass(frozen=True)
class SnapshotManifest:
    cairn_snapshot_version: int
    snapshot_id: str
    created_at: str
    label: str | None
    git_commit: str | None
    ledger_sha256: str
    sessions: tuple[str, ...]
    cas_hashes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "cairn_snapshot_version": self.cairn_snapshot_version,
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at,
            "label": self.label,
            "git_commit": self.git_commit,
            "ledger_sha256": self.ledger_sha256,
            "sessions": list(self.sessions),
            "cas_hashes": list(self.cas_hashes),
        }
