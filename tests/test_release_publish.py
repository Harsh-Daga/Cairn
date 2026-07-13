"""Release publication state checks."""

from __future__ import annotations

from urllib.error import HTTPError

import pytest

from scripts import check_pypi_version


def test_package_identity_matches_project_metadata() -> None:
    assert check_pypi_version.package_identity() == ("cairn-workspace", "1.0.1")


def test_version_is_published_returns_false_for_pypi_404(monkeypatch: pytest.MonkeyPatch) -> None:
    def not_found(*_args: object, **_kwargs: object) -> object:
        raise HTTPError("https://pypi.org", 404, "not found", {}, None)

    monkeypatch.setattr(check_pypi_version, "urlopen", not_found)
    assert check_pypi_version.version_is_published("cairn-workspace", "1.0.1") is False


def test_version_is_published_raises_for_non_404_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> object:
        raise HTTPError("https://pypi.org", 503, "unavailable", {}, None)

    monkeypatch.setattr(check_pypi_version, "urlopen", unavailable)
    with pytest.raises(RuntimeError, match="HTTP 503"):
        check_pypi_version.version_is_published("cairn-workspace", "1.0.1")
