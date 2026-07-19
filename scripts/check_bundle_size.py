#!/usr/bin/env python3
"""Enforce the stable gzip budget for first-party JavaScript bundles."""

from __future__ import annotations

import gzip
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "server" / "static" / "assets"
STATIC_FILE_ASSETS = ROOT / "server" / "static_file" / "assets"
INDEX_HTML = ROOT / "server" / "static" / "index.html"
MAX_JS_GZIP_BYTES = 350 * 1024
MAX_ENTRY_GZIP_BYTES = 150 * 1024
# file:// IIFE inlines lazy routes; keep separate from route-split HTTP totals.
MAX_STATIC_IIFE_GZIP_BYTES = 240 * 1024


def main() -> None:
    bundles = sorted(ASSETS.glob("*.js"))
    if not bundles:
        raise SystemExit("No built JavaScript bundles found under server/static/assets")
    sizes = {path.name: len(gzip.compress(path.read_bytes(), mtime=0)) for path in bundles}
    total = sum(sizes.values())
    print(f"JavaScript gzip total: {total} bytes across {len(sizes)} bundle(s)")
    html = INDEX_HTML.read_text(encoding="utf-8")
    match = re.search(r'<script[^>]+type="module"[^>]+src="/assets/([^"]+\.js)"', html)
    if match is None:
        raise SystemExit("Could not identify the module entry from server/static/index.html")
    entry_name = match.group(1)
    entry = sizes.get(entry_name)
    if entry is None:
        raise SystemExit(f"HTML module entry is missing from built assets: {entry_name}")
    print(f"JavaScript entry gzip: {entry} bytes")
    if entry > MAX_ENTRY_GZIP_BYTES:
        raise SystemExit(f"JavaScript entry budget exceeded: {entry} > {MAX_ENTRY_GZIP_BYTES}")
    if total > MAX_JS_GZIP_BYTES:
        details = "\n".join(f"  {name}: {size}" for name, size in sizes.items())
        raise SystemExit(
            f"JavaScript gzip budget exceeded: {total} > {MAX_JS_GZIP_BYTES}\n{details}"
        )
    static_bundles = sorted(STATIC_FILE_ASSETS.glob("*.js"))
    if len(static_bundles) != 1:
        raise SystemExit(f"Expected one static file IIFE bundle, found {len(static_bundles)}")
    static_size = len(gzip.compress(static_bundles[0].read_bytes(), mtime=0))
    print(f"Static file IIFE gzip: {static_size} bytes")
    if static_size > MAX_STATIC_IIFE_GZIP_BYTES:
        raise SystemExit(
            f"Static file IIFE gzip budget exceeded: {static_size} > {MAX_STATIC_IIFE_GZIP_BYTES}"
        )


if __name__ == "__main__":
    main()
