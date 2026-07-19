#!/usr/bin/env python3
"""Validate that a release runs from the annotated tag matching package metadata."""

from __future__ import annotations

import re
import subprocess
import sys

from server import __version__

TAG_RE = re.compile(r"^v(?P<version>(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))$")


def validate(tag: str) -> None:
    match = TAG_RE.fullmatch(tag)
    if match is None:
        raise ValueError(f"release tag must be vMAJOR.MINOR.PATCH, got {tag!r}")
    if match.group("version") != __version__:
        raise ValueError(f"tag {tag} does not match package version {__version__}")
    kind = subprocess.run(
        ["git", "cat-file", "-t", tag],
        check=False,
        capture_output=True,
        text=True,
    )
    if kind.returncode != 0 or kind.stdout.strip() != "tag":
        raise ValueError(f"{tag} must already exist as an annotated tag")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: validate_release_tag.py vMAJOR.MINOR.PATCH")
    try:
        validate(sys.argv[1])
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
