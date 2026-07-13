"""Phase 0 scaffold tests."""

from __future__ import annotations

import importlib
import pkgutil

import server


def test_server_package_importable() -> None:
    assert server.__version__ == "1.0.1"


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
