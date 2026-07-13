"""Project-path and CLI duration parsing tests."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from server.ingest.project_paths import parse_since


@pytest.mark.parametrize("value", ["1d", "2h", "30m", "0d"])
def test_parse_since_returns_a_utc_cutoff(value: str) -> None:
    cutoff = parse_since(value)
    assert cutoff.tzinfo is UTC
    assert cutoff <= datetime.now(UTC)


@pytest.mark.parametrize("value", ["", "days", "1x", "-1d"])
def test_parse_since_rejects_invalid_durations(value: str) -> None:
    with pytest.raises(ValueError, match="invalid --since|empty --since"):
        parse_since(value)
