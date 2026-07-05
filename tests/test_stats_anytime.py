"""Anytime-valid statistics property tests."""

from __future__ import annotations

import pytest

from server.improve.stats import anytime_valid_verdict

pytest.importorskip("hypothesis")
from hypothesis import given, settings
from hypothesis import strategies as st


@given(st.integers(min_value=20, max_value=200))
@settings(max_examples=200, deadline=None)
def test_false_positive_rate_under_continuous_monitoring(n_streams: int) -> None:
    """Under H0, repeated anytime-valid monitoring should keep FPR near alpha."""
    alpha = 0.05
    false_positives = 0
    for _ in range(n_streams):
        baseline = 1.0
        effect = 0.0
        se = 0.15
        rejected = False
        for n in range(5, 41):
            res = anytime_valid_verdict(
                effect,
                se,
                n=n,
                baseline=baseline,
                alpha=alpha,
            )
            if res.verdict in {"improved", "regressed"}:
                rejected = True
                break
        if rejected:
            false_positives += 1
    rate = false_positives / n_streams
    assert rate <= alpha + 0.02, f"FPR {rate:.3f} exceeds alpha+2% (seed stream={n_streams})"
