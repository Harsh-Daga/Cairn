"""Optional password-based encryption for exported reports and bundles."""

from __future__ import annotations

import hashlib
import secrets

_MAGIC = b"CAIRNENC1"


def encrypt_bytes(data: bytes, password: str) -> bytes:
    """Encrypt bytes with a password-derived key (local export obfuscation)."""
    if not password:
        msg = "password is required"
        raise ValueError(msg)
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000, dklen=32)
    stream = _stretch_key(key, len(data))
    ciphertext = bytes(a ^ b for a, b in zip(data, stream, strict=True))
    return _MAGIC + salt + ciphertext


def decrypt_bytes(payload: bytes, password: str) -> bytes:
    """Decrypt bytes produced by ``encrypt_bytes``."""
    if not payload.startswith(_MAGIC):
        msg = "invalid encrypted payload"
        raise ValueError(msg)
    salt = payload[len(_MAGIC) : len(_MAGIC) + 16]
    ciphertext = payload[len(_MAGIC) + 16 :]
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000, dklen=32)
    stream = _stretch_key(key, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, stream, strict=True))


def _stretch_key(key: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + counter.to_bytes(4, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])
