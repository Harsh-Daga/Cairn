"""Tail analytics tests."""

from __future__ import annotations

import numpy as np

from server.analyze.tail import p_exceed, return_level


def test_return_level_monotonic_with_n_future() -> None:
    xs = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0])
    low = return_level(xs, 10)
    high = return_level(xs, 1000)
    assert high >= low


def test_p_exceed_empirical() -> None:
    xs = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    assert p_exceed(xs, 3.0) == 0.4
