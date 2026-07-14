"""Release publication state checks."""

from __future__ import annotations

import tomllib
from pathlib import Path
from urllib.error import HTTPError

import pytest

from scripts import check_pypi_version

ROOT = Path(__file__).resolve().parent.parent
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
PACKAGE_IDENTITY = (str(PROJECT["name"]), str(PROJECT["version"]))


def test_package_identity_matches_project_metadata() -> None:
    assert check_pypi_version.package_identity() == PACKAGE_IDENTITY


def test_version_is_published_returns_false_for_pypi_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_found(*_args: object, **_kwargs: object) -> object:
        raise HTTPError("https://pypi.org", 404, "not found", {}, None)

    monkeypatch.setattr(check_pypi_version, "urlopen", not_found)
    assert check_pypi_version.version_is_published(*PACKAGE_IDENTITY) is False


def test_version_is_published_raises_for_non_404_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise HTTPError("https://pypi.org", 503, "unavailable", {}, None)

    monkeypatch.setattr(check_pypi_version, "urlopen", unavailable)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        check_pypi_version.version_is_published(*PACKAGE_IDENTITY)
