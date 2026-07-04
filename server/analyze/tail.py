"""EVT tail risk — GPD fit over session badness."""

from __future__ import annotations

import numpy as np


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
    return xi, max(sigma, 1e-9)


def expected_worst(exceedances: np.ndarray, n_future: int) -> float:
    """Expected maximum exceedance among n_future sessions (simple GPD tail)."""
    xi, sigma = fit_gpd_exceedances(exceedances)
    threshold = float(np.min(exceedances))
    if abs(xi) < 1e-6:
        return threshold + sigma * float(np.log(max(n_future, 1)))
    tail = (sigma / xi) * (float(n_future) ** xi - 1.0)
    return float(threshold + max(tail, 0.0))
