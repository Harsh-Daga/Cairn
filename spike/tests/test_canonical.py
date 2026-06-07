"""Golden-hash tests for canonical serialization (R1, Coding Rule #6)."""

from __future__ import annotations

import pytest

from spike.canonical import CanonicalError, canonical_json, hash_bytes, hash_obj, merkle_hash


def test_canonical_json_sorts_keys() -> None:
    assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_canonical_json_normalizes_floats() -> None:
    assert canonical_json({"temperature": 0.0}) == '{"temperature":"0"}'
    assert canonical_json({"temperature": 0}) == '{"temperature":0}'


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(CanonicalError):
        canonical_json({"x": float("nan")})


def test_hash_bytes_raw() -> None:
    assert (
        hash_bytes(b"hello") == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )


def test_hash_obj_golden() -> None:
    digest = hash_obj({"cairn_key_version": 1, "kind": "chat", "model": "gpt-4o-mini"})
    assert digest == "09b194ea278f50fa37b65d594b1bee27cbb16611d6810ac81a4c5dc5619c1575"


def test_merkle_hash_empty() -> None:
    assert merkle_hash() == hash_bytes(b"")


def test_merkle_hash_order_independent() -> None:
    a = hash_bytes(b"a")
    b = hash_bytes(b"b")
    assert merkle_hash(a, b) == merkle_hash(b, a)
