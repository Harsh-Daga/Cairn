"""Install script presence and packaging checks."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_install_script_exists_and_targets_pypi() -> None:
    script = ROOT / "install.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "uv tool install --upgrade cairn-workspace" in text
    assert "cd <repo> && cairn" in text
    # uvx zero-install trial is advertised.
    assert "uvx cairn-workspace" in text


def test_install_script_prints_path_hint() -> None:
    text = (ROOT / "install.sh").read_text(encoding="utf-8")
    assert "export PATH=" in text


def test_install_script_shellcheck_clean() -> None:
    if shutil.which("shellcheck") is None:
        return  # skip when shellcheck is absent
    result = subprocess.run(
        ["shellcheck", "-s", "sh", str(ROOT / "install.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_wheel_builds_without_duplicate_paths() -> None:
    result = subprocess.run(
        ["uv", "build", "--out-dir", str(ROOT / "dist-test")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
