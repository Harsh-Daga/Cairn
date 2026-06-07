"""Unified cache store: CAS + Action Cache via shared Ledger (R2, R14)."""

from __future__ import annotations

from pathlib import Path

from cairn.cache.cas import ContentAddressableStore
from cairn.ledger.ledger import Ledger


class CacheStore:
    """Filesystem CAS + SQLite AC (ledger.db)."""

    def __init__(self, project_root: Path) -> None:
        cairn_dir = project_root / ".cairn"
        self.ledger = Ledger(cairn_dir / "ledger.db")
        self.cas = ContentAddressableStore(cairn_dir)

    @property
    def ac(self) -> object:
        return self.ledger.ac

    def close(self) -> None:
        self.ledger.close()

    def get_output_hash(self, key: str) -> str | None:
        return self.ledger.ac.get(key)

    def has_blob(self, digest: str) -> bool:
        return self.cas.has(digest)

    def read_blob(self, digest: str) -> bytes | None:
        return self.cas.read(digest)

    def bind(self, key: str, data: bytes, *, kind: str, model: str) -> str:
        digest = self.cas.put(data)
        self.ledger.ac.put(key, digest, kind=kind, model=model)
        return digest

    def invalidate(self, key: str) -> None:
        self.ledger.ac.delete(key)
