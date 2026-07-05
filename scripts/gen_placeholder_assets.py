#!/usr/bin/env python3
"""Create placeholder PNG/GIF assets for README until L7 capture."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "docs" / "assets"

# Minimal 1-frame GIF (placeholder loop)
MINIMAL_GIF = (
    b"GIF89a\x01\x00\x01\x00\x80\x00\x00\xaa\x99\x77"
    b"\xff\xff\xff!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00"
    b"\x01\x00\x01\x00\x00\x02\x02D\x01\x00;"
)


def _png(w: int, h: int, rgb: tuple[int, int, int], label: str) -> bytes:
    """Write a flat-color PNG with embedded label text omitted (filename carries label)."""
    del label
    row = b"\x00" + bytes(rgb) * w
    raw = row * h
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        crc = struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + tag + data + crc

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    signature = b"\x89PNG\r\n\x1a\n"
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    placeholders = {
        "overview.png": (640, 360, (42, 38, 34)),
        "session-detail.png": (640, 360, (58, 52, 46)),
        "optimize-verdict.png": (640, 360, (74, 66, 58)),
        "favicon.png": (32, 32, (170, 153, 119)),
    }
    for name, (w, h, rgb) in placeholders.items():
        path = ASSETS / name
        path.write_bytes(_png(w, h, rgb, name))
        print(f"Wrote {path}")
    gif_path = ASSETS / "hero.gif"
    gif_path.write_bytes(MINIMAL_GIF)
    print(f"Wrote {gif_path}")


if __name__ == "__main__":
    main()
