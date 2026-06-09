"""Incremental ingest cursors under .cairn/watch/ (Phase 20)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FileCursor:
    path: str
    mtime_ns: int
    size: int

    def to_dict(self) -> dict[str, int | str]:
        return {"path": self.path, "mtime_ns": self.mtime_ns, "size": self.size}


class IngestCursors:
    """Track last-seen transcript files to skip unchanged paths on ingest."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.path = self.project_root / ".cairn" / "watch" / "cursors.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: dict[str, FileCursor] = {}
        self._load()

    def is_unchanged(self, file_path: Path) -> bool:
        resolved = str(file_path.resolve())
        stat = file_path.stat()
        previous = self._entries.get(resolved)
        if previous is None:
            return False
        return previous.mtime_ns == stat.st_mtime_ns and previous.size == stat.st_size

    def mark(self, file_path: Path) -> None:
        stat = file_path.stat()
        resolved = str(file_path.resolve())
        self._entries[resolved] = FileCursor(
            path=resolved,
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
        )

    def save(self) -> None:
        payload = {
            "version": 1,
            "files": [entry.to_dict() for entry in self._entries.values()],
        }
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def _load(self) -> None:
        if not self.path.is_file():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        for row in data.get("files", []):
            cursor = FileCursor(
                path=str(row["path"]),
                mtime_ns=int(row["mtime_ns"]),
                size=int(row["size"]),
            )
            self._entries[cursor.path] = cursor
