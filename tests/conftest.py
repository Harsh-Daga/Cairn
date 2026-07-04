"""Shared pytest fixtures."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def _reset_token_calibration() -> None:
    from cairn.ingest import tokenize

    tokenize.reset_calibration()
    yield
    tokenize.reset_calibration()


@pytest.fixture(scope="session")
def project_root() -> Path:
    return ROOT


@pytest.fixture
def cli_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return env


def run_cairn(
    *args: str,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    run_env = os.environ.copy()
    run_env["PYTHONPATH"] = str(ROOT) + os.pathsep + run_env.get("PYTHONPATH", "")
    if env:
        run_env.update(env)
    return subprocess.run(
        [sys.executable, "-m", "cairn", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        env=run_env,
    )
