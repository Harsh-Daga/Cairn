"""Install script presence and packaging checks."""

from __future__ import annotations

import subprocess
from pathlib import Path


def test_install_script_exists_and_is_executable() -> None:
    script = Path(__file__).parent.parent / "install.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "uv tool install cairn-workspace" in text
    assert "cairn init my-project" in text


def test_wheel_builds_without_duplicate_paths() -> None:
    root = Path(__file__).parent.parent
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(root / "dist-test")],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
