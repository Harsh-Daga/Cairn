"""EVT tail risk — GPD fit over session badness."""

from __future__ import annotations

import numpy as np


def _clamp_xi(xi: float) -> float:
    return float(np.clip(xi, -0.5, 0.9))


def fit_gpd_exceedances(exceedances: np.ndarray) -> tuple[float, float]:
    """Method-of-moments GPD shape (xi) and scale (sigma) for exceedances > 0."""
    if exceedances.size < 5:
        msg = "need at least 5 exceedances"
        raise ValueError(msg)
    x = exceedances.astype(float)
    mean = float(np.mean(x))
    var = float(np.var(x))
    if var <= 0 or mean <= 0:
        return 0.0, mean
    xi = 0.5 * (mean * mean / var - 1.0)
    sigma = 0.5 * mean * (mean * mean / var + 1.0)
    return _clamp_xi(xi), max(sigma, 1e-9)


def return_level(
    exceedances: np.ndarray,
    n_future: int,
    *,
    threshold: float | None = None,
) -> float:
    """Return-level (expected worst exceedance) among n_future sessions."""
    if exceedances.size == 0:
        return 0.0
    u = float(threshold if threshold is not None else np.percentile(exceedances, 90))
    tail = exceedances[exceedances > u] - u
    if tail.size < 5:
        return float(u + float(np.max(exceedances)))
    xi, sigma = fit_gpd_exceedances(tail)
    if abs(xi) < 1e-6:
        return float(u + sigma * float(np.log(max(n_future, 1))))
    level = u + (sigma / xi) * (float(n_future) ** xi - 1.0)
    return float(max(level, u))


def p_exceed(exceedances: np.ndarray, threshold: float) -> float:
    """Empirical probability a session exceeds threshold."""
    if exceedances.size == 0:
        return 0.0
    return float(np.mean(exceedances > threshold))


def expected_worst(exceedances: np.ndarray, n_future: int) -> float:
    """Backward-compatible alias for return_level."""
    return return_level(exceedances, n_future)
