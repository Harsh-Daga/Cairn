"""AMDM math utilities for behavioral fingerprints."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

VECTOR_DIM = 24

# χ² critical values at p=0.99 for df 1..8.
_CHI2_99 = {1: 6.635, 2: 9.210, 3: 11.345, 4: 13.277, 5: 15.086, 6: 16.812, 7: 18.475, 8: 20.090}


@dataclass
class DriftResult:
    drift: bool
    d_squared: float | None
    threshold: float | None
    d_eff: int
    per_dim_deltas: list[float]
    distance: float | None
    kind: str
    data_notes: list[str] = field(default_factory=list)


def pca_reduce(
    baseline: list[list[float]], *, d_eff: int | None = None
) -> tuple[np.ndarray, np.ndarray, int]:
    """Return (mean, components, d_eff) for PCA on baseline vectors."""
    matrix = np.array(baseline, dtype=float)
    if matrix.ndim != 2 or matrix.shape[0] < 2:
        return np.zeros(VECTOR_DIM), np.zeros((0, VECTOR_DIM)), 0
    mean = matrix.mean(axis=0)
    centered = matrix - mean
    try:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
    except np.linalg.LinAlgError:
        return mean, np.zeros((0, VECTOR_DIM)), 0
    max_d = min(8, max(3, matrix.shape[0] - 1, 3))
    max_d = min(max_d, vt.shape[0])
    if d_eff is not None:
        max_d = min(max_d, max(3, d_eff))
    max_d = max(3, min(8, max_d))
    if max_d > vt.shape[0]:
        max_d = vt.shape[0]
    components = vt[:max_d]
    return mean, components, max_d


def mahalanobis_distance(x: np.ndarray, mean: np.ndarray, cov_inv: np.ndarray) -> float:
    """Compute squared Mahalanobis distance."""
    diff = (x - mean).reshape(-1, 1)
    if cov_inv.size == 0:
        return 0.0
    value = diff.T @ cov_inv @ diff
    return float(np.asarray(value).ravel()[0])


def detect_drift(current: list[float], baseline: list[list[float]]) -> DriftResult:
    """Joint-shock drift: Mahalanobis D² vs χ² threshold in PCA space."""
    if len(baseline) < 4:
        return DriftResult(
            drift=False,
            d_squared=None,
            threshold=None,
            d_eff=0,
            per_dim_deltas=[],
            distance=None,
            kind="insufficient_baseline",
            data_notes=[f"baseline has {len(baseline)} sessions; need >=4 for AMDM"],
        )
    mean_full, components, d_eff = pca_reduce(baseline)
    if d_eff < 3 or components.shape[0] == 0:
        return DriftResult(
            drift=False,
            d_squared=None,
            threshold=None,
            d_eff=0,
            per_dim_deltas=[],
            distance=None,
            kind="insufficient_baseline",
            data_notes=["PCA could not extract >=3 dims from baseline"],
        )
    matrix = np.array(baseline, dtype=float)
    reduced = (matrix - mean_full) @ components.T
    cov = np.cov(reduced, rowvar=False)
    try:
        cov_inv = np.linalg.pinv(cov)
    except np.linalg.LinAlgError:
        return DriftResult(
            drift=False,
            d_squared=None,
            threshold=None,
            d_eff=d_eff,
            per_dim_deltas=[],
            distance=None,
            kind="insufficient_baseline",
            data_notes=["covariance not invertible"],
        )
    x_reduced = (np.array(current, dtype=float) - mean_full) @ components.T
    d_squared = mahalanobis_distance(x_reduced, np.zeros(d_eff), cov_inv)
    threshold = _CHI2_99.get(d_eff, 20.090)
    std = np.sqrt(np.clip(np.diag(cov), 1e-9, None))
    per_dim = [float(v) for v in (x_reduced / std).tolist()]
    drift = d_squared > threshold
    return DriftResult(
        drift=drift,
        d_squared=round(d_squared, 4),
        threshold=float(threshold),
        d_eff=d_eff,
        per_dim_deltas=[round(z, 3) for z in per_dim],
        distance=round(math.sqrt(max(0.0, d_squared)), 4),
        kind="joint_shock" if drift else "none",
    )


def detect_gradual_drift(
    weekly_means: list[tuple[str, list[float]]], axis_labels: list[str]
) -> dict[str, object]:
    """Per-axis EWMA with adaptive 3σ bounds and sustained-shift detection."""
    if len(weekly_means) < 3:
        return {
            "drift": False,
            "axes": [],
            "data_notes": ["need >=3 weekly means for gradual drift"],
        }
    vectors = np.array([vector for _, vector in weekly_means], dtype=float)
    count = vectors.shape[0]
    anchor_count = max(2, count // 3)
    anchor = vectors[:anchor_count]
    anchor_mean = anchor.mean(axis=0)
    anchor_std = np.clip(anchor.std(axis=0), 1e-6, None)
    lower = anchor_mean - 3 * anchor_std
    upper = anchor_mean + 3 * anchor_std

    drifting_axes: list[dict[str, object]] = []
    for axis in range(vectors.shape[1]):
        series = vectors[:, axis]
        alpha = 0.4
        ewma = float(series[0])
        ewma_path = [ewma]
        for value in series[1:]:
            ewma = alpha * float(value) + (1 - alpha) * ewma
            ewma_path.append(ewma)
        outside = [not (lower[axis] <= value <= upper[axis]) for value in ewma_path]
        streak = 0
        for is_outside in reversed(outside):
            if is_outside:
                streak += 1
                continue
            break
        if streak >= 2:
            label = axis_labels[axis] if 0 <= axis < len(axis_labels) else f"axis {axis}"
            drifting_axes.append(
                {
                    "axis": axis,
                    "axis_label": label,
                    "weeks_outside": streak,
                    "ewma": round(float(ewma_path[-1]), 4),
                    "bounds": [round(float(lower[axis]), 4), round(float(upper[axis]), 4)],
                }
            )
    return {
        "drift": bool(drifting_axes),
        "axes": drifting_axes,
        "data_notes": [] if drifting_axes else ["all axes within 3σ EWMA bounds"],
    }


def fingerprint_distance(current: list[float], baseline: list[list[float]]) -> float | None:
    """Scalar Mahalanobis distance helper."""
    result = detect_drift(current, baseline)
    return result.distance
