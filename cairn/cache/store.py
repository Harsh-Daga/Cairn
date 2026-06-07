"""Unified cache store: CAS + Action Cache (R2)."""

from __future__ import annotations

from pathlib import Path

from cairn.cache.action_cache import ActionCache
from cairn.cache.cas import ContentAddressableStore


class CacheStore:
  """Filesystem CAS + SQLite AC."""

  def __init__(self, project_root: Path) -> None:
      cairn_dir = project_root / ".cairn"
      self.cas = ContentAddressableStore(cairn_dir)
      self.ac = ActionCache(cairn_dir / "ledger.db")

  def close(self) -> None:
      self.ac.close()

  def get_output_hash(self, key: str) -> str | None:
      return self.ac.get(key)

  def has_blob(self, digest: str) -> bool:
      return self.cas.has(digest)

  def read_blob(self, digest: str) -> bytes | None:
      return self.cas.read(digest)

  def bind(self, key: str, data: bytes, *, kind: str, model: str) -> str:
      digest = self.cas.put(data)
      self.ac.put(key, digest, kind=kind, model=model)
      return digest

  def invalidate(self, key: str) -> None:
      self.ac.delete(key)
