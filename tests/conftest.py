"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from cairn.cli import init_cmd


@pytest.fixture
def project_dir(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    init_cmd.run(argparse_namespace(root))
    return root


def argparse_namespace(root: Path) -> object:
    import argparse

    return argparse.Namespace(dir=root)


@pytest.fixture
def fixtures_dir(tmp_path: Path) -> Path:
    return tmp_path / "fixtures"
