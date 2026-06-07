"""Content-addressable store on filesystem (R2)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from cairn.util.canonical import hash_bytes


def _fsync_dir(path: Path) -> None:
    dir_fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)


class ContentAddressableStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.cas_dir = root / "cache" / "cas"
        self.tmp_dir = root / "tmp"
        self.cas_dir.mkdir(parents=True, exist_ok=True)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, digest: str) -> Path:
        return self.cas_dir / digest[:2] / digest

    def has(self, digest: str) -> bool:
        return self._path(digest).is_file()

    def read(self, digest: str) -> bytes | None:
        path = self._path(digest)
        if not path.is_file():
            return None
        return path.read_bytes()

    def put(self, data: bytes) -> str:
        digest = hash_bytes(data)
        final = self._path(digest)
        if final.exists():
            return digest
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.tmp_dir / f"{uuid.uuid4()}.blob"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
        try:
            os.write(fd, data)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(tmp, final)
        _fsync_dir(final.parent)
        return digest
