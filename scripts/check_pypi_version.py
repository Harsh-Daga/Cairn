#!/usr/bin/env python3
"""Return whether the configured package version is absent from PyPI.

Exit codes: 0 means unpublished (safe to publish), 1 means already published,
and 2 means the release state could not be determined.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent


def package_identity(pyproject: Path = ROOT / "pyproject.toml") -> tuple[str, str]:
    """Read the normalized project name and version from project metadata."""
    with pyproject.open("rb") as handle:
        project = tomllib.load(handle)["project"]
    return str(project["name"]), str(project["version"])


def version_is_published(name: str, version: str) -> bool:
    """Return whether a package version exists on PyPI."""
    url = f"https://pypi.org/pypi/{name}/{version}/json"
    try:
        with urlopen(url, timeout=10):  # noqa: S310 - fixed PyPI API endpoint
            return True
    except HTTPError as exc:
        if exc.code == 404:
            return False
        raise RuntimeError(f"PyPI returned HTTP {exc.code} for {name} {version}") from exc
    except URLError as exc:
        raise RuntimeError(f"Unable to reach PyPI for {name} {version}: {exc.reason}") from exc


def main() -> int:
    name, version = package_identity()
    if version_is_published(name, version):
        print(f"{name} {version} is already published; skipping upload.")
        return 1
    print(f"{name} {version} is unpublished and ready to upload.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"release-state check failed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
