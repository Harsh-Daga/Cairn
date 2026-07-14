"""Phase 0 scaffold tests."""

from __future__ import annotations

import importlib
import pkgutil
import tomllib
from pathlib import Path

import server


def test_server_package_importable() -> None:
    root = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    assert server.__version__ == pyproject["project"]["version"]


def test_all_server_submodules_importable() -> None:
    """Every scaffold module under server/ must import without error."""
    prefix = server.__name__ + "."
    failures: list[str] = []
    for _finder, name, _ispkg in pkgutil.walk_packages(server.__path__, prefix):
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 — collect all import failures
            failures.append(f"{name}: {exc}")
    assert not failures, "Import failures:\n" + "\n".join(failures)


def test_incremental_view_is_abstract() -> None:
    from abc import ABC

    from server.analyze.views import IncrementalView

    assert issubclass(IncrementalView, ABC)
