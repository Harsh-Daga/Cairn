"""Canonical JSON/hashing primitives + run-id resolution."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass
from typing import Any

from cairn.ledger.ledger import Ledger


class CanonicalError(ValueError):
    """Raised when a value cannot be canonically encoded."""


def _normalize_float(value: float) -> str:
    if math.isnan(value) or math.isinf(value):
        msg = f"non-finite float cannot be hashed: {value!r}"
        raise CanonicalError(msg)
    text = format(value, ".15g")
    return "0" if text in {"-0", "-0.0"} else text


def _canonicalize(obj: Any) -> Any:
    if obj is None or isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return _normalize_float(obj)
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, bytes):
        msg = "bytes must be hashed raw via hash_bytes(), not embedded in canonical JSON"
        raise CanonicalError(msg)
    if isinstance(obj, list):
        return [_canonicalize(item) for item in obj]
    if isinstance(obj, dict):
        return {
            unicodedata.normalize("NFC", str(key)): _canonicalize(value)
            for key, value in sorted(obj.items(), key=lambda pair: str(pair[0]))
        }
    msg = f"unsupported type for canonical JSON: {type(obj).__name__}"
    raise CanonicalError(msg)


def canonical_json(obj: Any) -> str:
    """Deterministic JSON for hashing."""
    return json.dumps(_canonicalize(obj), ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def hash_bytes(data: bytes) -> str:
    """SHA-256 of raw bytes, lowercase hex."""
    return hashlib.sha256(data).hexdigest()


def hash_obj(obj: Any) -> str:
    """SHA-256 of canonical JSON."""
    return hash_bytes(canonical_json(obj).encode("utf-8"))


class IdNotFoundError(ValueError):
    def __init__(self, token: str) -> None:
        self.token = token
        super().__init__(f"no session or run matches '{token}'")


class AmbiguousIdError(ValueError):
    def __init__(self, token: str, candidates: list[str]) -> None:
        self.token = token
        self.candidates = candidates
        shown = ", ".join(candidates[:10])
        extra = "" if len(candidates) <= 10 else f" (+{len(candidates) - 10} more)"
        super().__init__(f"ambiguous id '{token}' matches {len(candidates)}: {shown}{extra}")


@dataclass(frozen=True)
class ResolvedId:
    run_id: str
    external_id: str | None
    source: str | None

    @property
    def display_id(self) -> str:
        return self.external_id or self.run_id


def _str_or_none(value: object) -> str | None:
    return str(value) if value is not None else None


def resolve_id(ledger: Ledger, token: str) -> ResolvedId:
    conn = ledger.connection
    if not token or token == "last":
        latest = conn.execute(
            "SELECT run_id, external_id, source FROM runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if latest is None:
            raise IdNotFoundError(token or "last")
        return ResolvedId(str(latest["run_id"]), latest["external_id"], latest["source"])

    rows = conn.execute("SELECT run_id, external_id, source FROM runs").fetchall()
    exact = [tuple(r) for r in rows if r[0] == token or (r[1] is not None and r[1] == token)]
    if len(exact) == 1:
        return ResolvedId(str(exact[0][0]), exact[0][1], exact[0][2])
    if len(exact) > 1:
        raise AmbiguousIdError(token, sorted({str(r[0]) for r in exact}))

    matched: dict[str, tuple[object, ...]] = {}
    for r in rows:
        run_id = str(r[0])
        ext = str(r[1]) if r[1] is not None else ""
        if run_id.startswith(token) or (ext and ext.startswith(token)):
            matched[run_id] = tuple(r)
    if len(matched) == 1:
        t = next(iter(matched.values()))
        return ResolvedId(str(t[0]), _str_or_none(t[1]), _str_or_none(t[2]))
    if len(matched) > 1:
        raise AmbiguousIdError(token, sorted(matched))
    raise IdNotFoundError(token)
