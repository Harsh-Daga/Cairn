"""Generate the committed configuration reference from the typed schema."""

from __future__ import annotations

import argparse
from pathlib import Path

from server.configuration import configuration_reference_markdown

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "configuration-reference.md"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    expected = configuration_reference_markdown()
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != expected:
            print(f"{OUTPUT.relative_to(ROOT)} is stale; run this generator")
            return 1
        print(f"{OUTPUT.relative_to(ROOT)} is current")
        return 0
    OUTPUT.write_text(expected, encoding="utf-8")
    print(f"Wrote {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
