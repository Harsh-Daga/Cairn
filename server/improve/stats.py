"""CUPED + sequential test + clustered ESS."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

Z_95 = 1.96
DEFAULT_RHO = 0.3


@dataclass
class CausalResult:
    effect_estimate: float | None
    effect_ci_low: float | None
    effect_ci_high: float | None
    verdict: str  # improved | regressed | no_effect | inconclusive | confounded
    test_method: str
    confound_flag: bool
    data_notes: list[str]


def _model_mix(conn: sqlite3.Connection, run_ids: list[str]) -> dict[str, float]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" * len(run_ids))
    sql = (
        f"SELECT model, COUNT(*) AS n FROM traces "
        f"WHERE trace_id IN ({placeholders}) GROUP BY model"
    )
    rows = conn.execute(sql, run_ids).fetchall()
    total = sum(int(r[1]) for r in rows)
    if total == 0:
        return {}
    return {str(r[0]): int(r[1]) / total for r in rows}


def _mix_shift(
    before: dict[str, float], after: dict[str, float], *, threshold: float = 0.15
) -> bool:
    keys = set(before) | set(after)
    return any(abs(before.get(k, 0.0) - after.get(k, 0.0)) > threshold for k in keys)


def cuped_adjust(
    outcomes: list[float],
    covariates: list[float],
) -> tuple[float, float]:
    """Return (adjusted_mean, se) using covariate as pre-period expectation."""
    n = len(outcomes)
    if n < 2 or len(covariates) != n:
        mean = sum(outcomes) / n if n else 0.0
        se = _se(outcomes)
        return mean, se
    mx = sum(covariates) / n
    my = sum(outcomes) / n
    var_x = sum((x - mx) ** 2 for x in covariates) / max(n - 1, 1)
    if var_x <= 0:
        return my, _se(outcomes)
    cov_xy = sum((outcomes[i] - my) * (covariates[i] - mx) for i in range(n)) / max(n - 1, 1)
    theta = cov_xy / var_x
    adjusted = [outcomes[i] - theta * (covariates[i] - mx) for i in range(n)]
    return sum(adjusted) / n, _se(adjusted)


def _se(xs: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var / n)


def sequential_verdict(
    effect: float,
    se: float,
    *,
    n: int,
    min_n: int = 5,
) -> CausalResult:
    """Group-sequential style CI; honest inconclusive when evidence thin."""
    notes: list[str] = []
    if n < min_n:
        return CausalResult(
            effect_estimate=effect if n else None,
            effect_ci_low=None,
            effect_ci_high=None,
            verdict="inconclusive",
            test_method="group_sequential",
            confound_flag=False,
            data_notes=[f"n={n} < {min_n}: inconclusive"],
        )
    if se <= 0:
        se = abs(effect) * 0.1 or 1.0
        notes.append("se estimated from effect magnitude")
    ci_lo = effect - Z_95 * se
    ci_hi = effect + Z_95 * se
    if ci_hi < 0:
        verdict = "improved"
    elif ci_lo > 0:
        verdict = "regressed"
    elif abs(effect) < se:
        verdict = "no_effect"
    else:
        verdict = "inconclusive"
    return CausalResult(
        effect_estimate=round(effect, 4),
        effect_ci_low=round(ci_lo, 4),
        effect_ci_high=round(ci_hi, 4),
        verdict=verdict,
        test_method="group_sequential",
        confound_flag=False,
        data_notes=notes,
    )


def clustered_effective_n(
    values: list[float],
    clusters: list[str],
    *,
    rho: float = DEFAULT_RHO,
) -> float:
    """ESS = n / (1 + (m̄-1)ρ) with intraclass correlation rho."""
    n = len(values)
    if n == 0:
        return 0.0
    by_cluster: dict[str, int] = {}
    for cluster in clusters:
        by_cluster[cluster] = by_cluster.get(cluster, 0) + 1
    m_bar = sum(by_cluster.values()) / max(len(by_cluster), 1)
    if len(by_cluster) < 5:
        rho = DEFAULT_RHO
    return n / (1.0 + max(m_bar - 1.0, 0.0) * rho)


def measure_causal_effect(
    conn: sqlite3.Connection,
    *,
    pre_trace_ids: list[str],
    post_trace_ids: list[str],
    metric_fn: Callable[[str], float],
) -> CausalResult:
    """CUPED-adjusted before/after with confounder guard on model mix."""
    pre_out = [metric_fn(tid) for tid in pre_trace_ids]
    post_out = [metric_fn(tid) for tid in post_trace_ids]
    pre_cov = pre_out  # use pre-period as covariate baseline
    post_cov = (
        pre_cov[: len(post_out)]
        if len(pre_cov) >= len(post_out)
        else pre_cov + [0.0] * (len(post_out) - len(pre_cov))
    )
    if len(post_out) != len(post_cov):
        post_cov = [sum(pre_out) / len(pre_out) if pre_out else 0.0] * len(post_out)

    before_mix = _model_mix(conn, pre_trace_ids)
    after_mix = _model_mix(conn, post_trace_ids)
    if _mix_shift(before_mix, after_mix):
        return CausalResult(
            effect_estimate=None,
            effect_ci_low=None,
            effect_ci_high=None,
            verdict="confounded",
            test_method="cuped+sequential",
            confound_flag=True,
            data_notes=["model/task mix shifted between windows"],
        )

    pre_mean = sum(pre_out) / len(pre_out) if pre_out else 0.0
    adj_post, se = cuped_adjust(post_out, post_cov[: len(post_out)])
    effect = adj_post - pre_mean
    return sequential_verdict(effect, se, n=len(post_trace_ids))
