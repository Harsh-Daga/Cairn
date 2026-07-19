#!/usr/bin/env python3
"""Extract one version's checked-in changelog section for a GitHub Release."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"


def extract(version: str) -> str:
    text = CHANGELOG.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^## \[{re.escape(version)}\][^\n]*\n(?P<body>.*?)(?=^## \[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"CHANGELOG.md has no {version} release section")
    body = match.group("body").strip()
    if not body:
        raise ValueError(f"CHANGELOG.md {version} release section is empty")
    return body + "\n"


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: extract_release_notes.py VERSION OUTPUT")
    try:
        notes = extract(sys.argv[1])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output = Path(sys.argv[2])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(notes, encoding="utf-8")


if __name__ == "__main__":
    main()
