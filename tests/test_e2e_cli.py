"""End-to-end CLI smoke tests under RecordedProvider replay."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "cairn", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def test_init_validate_status_build(tmp_path: Path) -> None:
    root = tmp_path / "demo"
    assert _run("init", str(root), cwd=tmp_path).returncode == 0
    assert _run("validate", cwd=root).returncode == 0
    status = _run("status", cwd=root)
    assert status.returncode == 0
    assert "summaries:alpha" in status.stdout
    build = _run("build", "--yes", "--provider-mode", "recorded", cwd=root)
    assert build.returncode == 0
    assert (root / "outputs" / "report.md").is_file()
    second = _run("build", "--yes", "--provider-mode", "recorded", cwd=root)
    assert second.returncode == 0
    assert "tokens=0" in second.stdout
