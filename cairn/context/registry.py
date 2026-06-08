"""Scan and index project context assets."""

from __future__ import annotations

import fnmatch
import mimetypes
import sqlite3
import subprocess
from dataclasses import dataclass
from pathlib import Path

from cairn.context.config import ContextConfig, load_context_config
from cairn.ledger.schema import migrate
from cairn.ledger.storage import (
    ContextAssetRecord,
    list_context_assets,
    upsert_context_asset,
)
from cairn.util.canonical import hash_bytes


@dataclass(frozen=True)
class ContextAsset:
    path_rel: str
    content_hash: str
    mime: str | None
    git_blob: str | None
    tags: tuple[str, ...]
    updated_at: str

    @classmethod
    def from_record(cls, record: ContextAssetRecord) -> ContextAsset:
        return cls(
            path_rel=record.path_rel,
            content_hash=record.content_hash,
            mime=record.mime,
            git_blob=record.git_blob,
            tags=record.tags,
            updated_at=record.updated_at,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "path_rel": self.path_rel,
            "content_hash": self.content_hash,
            "mime": self.mime,
            "git_blob": self.git_blob,
            "tags": list(self.tags),
            "updated_at": self.updated_at,
        }


class ContextRegistry:
    """Indexes markdown, source, docs, and knowledge files for a project."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.config = load_context_config(self.project_root)
        cairn_dir = self.project_root / ".cairn"
        cairn_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = cairn_dir / "ledger.db"
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        migrate(self._conn)

    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def scan(self) -> list[ContextAsset]:
        """Walk project files and upsert context_assets in the ledger."""
        indexed: list[ContextAsset] = []
        for path in self._iter_files(self.config):
            rel = str(path.relative_to(self.project_root))
            data = path.read_bytes()
            record = upsert_context_asset(
                self._conn,
                path_rel=rel,
                content_hash=hash_bytes(data),
                mime=_guess_mime(path),
                git_blob=_git_blob(self.project_root, path),
                tags=_infer_tags(rel),
            )
            indexed.append(ContextAsset.from_record(record))
        return indexed

    def list_assets(self) -> list[ContextAsset]:
        return [ContextAsset.from_record(r) for r in list_context_assets(self._conn)]

    def resolve(self, selector: str) -> ContextAsset | None:
        """Resolve a repo-relative path or glob selector to a context asset."""
        assets = self.list_assets()
        if not assets:
            assets = self.scan()
        exact = [a for a in assets if a.path_rel == selector]
        if exact:
            return exact[0]
        matches = [a for a in assets if fnmatch.fnmatch(a.path_rel, selector)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            matches.sort(key=lambda a: a.path_rel)
            return matches[0]
        return None

    def _iter_files(self, config: ContextConfig) -> list[Path]:
        matched: set[Path] = set()
        for pattern in config.include:
            for path in self.project_root.glob(pattern):
                if path.is_file() and path.is_relative_to(self.project_root):
                    matched.add(path.resolve())
        filtered: list[Path] = []
        for path in sorted(matched):
            rel = str(path.relative_to(self.project_root))
            if _excluded(rel, config.exclude):
                continue
            filtered.append(path)
        return filtered


def _excluded(rel: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def _guess_mime(path: Path) -> str | None:
    mime, _ = mimetypes.guess_type(path.name)
    return mime


def _git_blob(project_root: Path, path: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "hash-object", str(path)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _infer_tags(path_rel: str) -> tuple[str, ...]:
    tags: list[str] = []
    if path_rel.startswith(("docs/", "inputs/", "context/")):
        tags.append("docs")
    if path_rel.startswith(("src/", "cairn/", "lib/", "app/")):
        tags.append("code")
    if path_rel.startswith("prompts/"):
        tags.append("prompts")
    if path_rel.endswith(".md"):
        tags.append("markdown")
    return tuple(tags)
