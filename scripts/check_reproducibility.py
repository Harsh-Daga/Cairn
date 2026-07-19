#!/usr/bin/env python3
"""Rebuild release inputs twice and require byte-identical local outputs."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "server" / "static"


def _files(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _run(command: list[str], *, env: dict[str, str]) -> None:
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def _compare(label: str, first: dict[str, str], second: dict[str, str]) -> None:
    if first == second:
        print(f"{label} reproducible: {len(first)} file(s)")
        return
    changed = sorted(
        name for name in first.keys() | second.keys() if first.get(name) != second.get(name)
    )
    raise RuntimeError(f"{label} rebuild differs: {', '.join(changed)}")


def main() -> None:
    env = os.environ.copy()
    timestamp = subprocess.run(
        ["git", "show", "-s", "--format=%ct", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    env["SOURCE_DATE_EPOCH"] = timestamp
    env["UV_FROZEN"] = "1"

    _run([sys.executable, "scripts/build_ui.py", "build"], env=env)
    static_first = _files(STATIC)
    _run([sys.executable, "scripts/build_ui.py", "build"], env=env)
    _compare("static assets", static_first, _files(STATIC))

    with tempfile.TemporaryDirectory(prefix="cairn-repro-") as tmp:
        first_dir = Path(tmp) / "first"
        second_dir = Path(tmp) / "second"
        _run(["uv", "build", "--out-dir", str(first_dir)], env=env)
        _run(["uv", "build", "--out-dir", str(second_dir)], env=env)
        _compare("wheel/sdist", _files(first_dir), _files(second_dir))


if __name__ == "__main__":
    main()
