"""CAS durability tests (R2)."""

from __future__ import annotations

from pathlib import Path

from cairn.cache.cas import ContentAddressableStore
from cairn.util.canonical import hash_bytes


def test_cas_put_roundtrip(tmp_path: Path) -> None:
    cas = ContentAddressableStore(tmp_path)
    data = b"hello cas"
    digest = cas.put(data)
    assert digest == hash_bytes(data)
    assert cas.read(digest) == data
    assert cas.has(digest)


def test_cas_corrupt_blob_does_not_match_digest(tmp_path: Path) -> None:
    cas = ContentAddressableStore(tmp_path)
    data = b"canonical bytes"
    digest = cas.put(data)
    path = cas._path(digest)
    path.write_bytes(b"truncated")
    raw = cas.read(digest)
    assert raw is not None
    assert hash_bytes(raw) != digest
