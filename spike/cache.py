"""Filesystem Action Cache + CAS for the spike (§9, R2 subset)."""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from spike.canonical import hash_bytes


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    tokens_spent: int = 0


class SpikeCache:
    """Minimal AC (JSON file) + CAS (sharded filesystem)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.cas_dir = root / "cache" / "cas"
        self.ac_path = root / "action_cache.json"
        self.cas_dir.mkdir(parents=True, exist_ok=True)
        self._ac: dict[str, str] = {}
        if self.ac_path.exists():
            self._ac = json.loads(self.ac_path.read_text(encoding="utf-8"))

    def _cas_path(self, digest: str) -> Path:
        return self.cas_dir / digest[:2] / digest

    def get_output_hash(self, key: str) -> str | None:
        return self._ac.get(key)

    def read_blob(self, digest: str) -> bytes | None:
        path = self._cas_path(digest)
        if not path.exists():
            return None
        return path.read_bytes()

    def put_blob(self, data: bytes) -> str:
        digest = hash_bytes(data)
        final = self._cas_path(digest)
        if final.exists():
            return digest
        final.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.root / "tmp" / f"{uuid.uuid4()}.blob"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_bytes(data)
        os.replace(tmp, final)
        return digest

    def bind(self, key: str, output_hash: str) -> None:
        self._ac[key] = output_hash
        self._flush_ac()

    def _flush_ac(self) -> None:
        tmp = self.root / "tmp" / f"{uuid.uuid4()}.ac"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(self._ac, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(tmp, self.ac_path)
