"""ULID generation — no external dependency."""

from __future__ import annotations

import os
import time

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid() -> str:
    """Generate a lexicographically sortable ULID string."""
    ts_ms = int(time.time() * 1000)
    ts_part = ""
    n = ts_ms
    for _ in range(10):
        ts_part = _CROCKFORD[n & 31] + ts_part
        n >>= 5
    rand_bytes = os.urandom(10)
    rand_part = ""
    acc = 0
    bits = 0
    for b in rand_bytes:
        acc = (acc << 8) | b
        bits += 8
        while bits >= 5:
            bits -= 5
            rand_part += _CROCKFORD[(acc >> bits) & 31]
    while len(rand_part) < 16:
        rand_part += _CROCKFORD[0]
    return ts_part + rand_part[:16]
