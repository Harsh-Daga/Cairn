"""Difference-in-means confidence sequences, confound guards, and clustered ESS."""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_RHO = 0.3
DEFAULT_ALPHA = 0.05
DEFAULT_TAU2 = 1.0
DEFAULT_PRACTICAL_DELTA_PCT = 0.02


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
        f"SELECT model, COUNT(*) AS n FROM traces WHERE trace_id IN ({placeholders}) GROUP BY model"
    )
    rows = conn.execute(sql, run_ids).fetchall()
    total = sum(int(r[1]) for r in rows)
    if total == 0:
        return {}
    return {str(r[0]): int(r[1]) / total for r in rows}


def _trace_field_mix(
    conn: sqlite3.Connection, run_ids: list[str], *, field: str
) -> dict[str, float]:
    if not run_ids:
        return {}
    columns = {"project": "project", "source": "source"}
    column = columns.get(field)
    if column is None:
        raise ValueError(f"unsupported trace mix field: {field}")
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        f"SELECT COALESCE({column}, '(unknown)'), COUNT(*) "  # noqa: S608 - allowlisted column
        f"FROM traces WHERE trace_id IN ({placeholders}) GROUP BY COALESCE({column}, '(unknown)')",
        run_ids,
    ).fetchall()
    return _normalized_counts(rows)


def _span_count_mix(conn: sqlite3.Connection, run_ids: list[str]) -> dict[str, float]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        "SELECT CASE WHEN span_count < 10 THEN '0-9' "
        "WHEN span_count < 25 THEN '10-24' WHEN span_count < 50 THEN '25-49' "
        f"ELSE '50+' END AS bucket, COUNT(*) FROM traces WHERE trace_id IN ({placeholders}) "
        "GROUP BY bucket",
        run_ids,
    ).fetchall()
    return _normalized_counts(rows)


def _tool_mix(conn: sqlite3.Connection, run_ids: list[str]) -> dict[str, float]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        "SELECT COALESCE(name, '(unknown)'), COUNT(*) FROM spans "
        f"WHERE kind = 'tool_call' AND trace_id IN ({placeholders}) "
        "GROUP BY COALESCE(name, '(unknown)')",
        run_ids,
    ).fetchall()
    return _normalized_counts(rows)


def _parser_version_mix(conn: sqlite3.Connection, run_ids: list[str]) -> dict[str, float]:
    if not run_ids:
        return {}
    placeholders = ",".join("?" * len(run_ids))
    rows = conn.execute(
        "SELECT COALESCE(parser_version, '(unknown)'), COUNT(*) FROM data_quality "
        f"WHERE trace_id IN ({placeholders}) GROUP BY COALESCE(parser_version, '(unknown)')",
        run_ids,
    ).fetchall()
    return _normalized_counts(rows)


def _normalized_counts(rows: list[sqlite3.Row]) -> dict[str, float]:
    total = sum(int(row[1]) for row in rows)
    if total == 0:
        return {}
    return {str(row[0]): int(row[1]) / total for row in rows}


def _mix_shift(
    before: dict[str, float], after: dict[str, float], *, threshold: float = 0.15
) -> bool:
    keys = set(before) | set(after)
    return any(abs(before.get(k, 0.0) - after.get(k, 0.0)) > threshold for k in keys)


def _confound_notes(
    conn: sqlite3.Connection, pre_trace_ids: list[str], post_trace_ids: list[str]
) -> list[str]:
    notes: list[str] = []
    if _mix_shift(_model_mix(conn, pre_trace_ids), _model_mix(conn, post_trace_ids)):
        notes.append("model mix shifted between windows")
    if _mix_shift(
        _trace_field_mix(conn, pre_trace_ids, field="project"),
        _trace_field_mix(conn, post_trace_ids, field="project"),
    ):
        notes.append("task mix shifted: project distribution changed")
    if _mix_shift(
        _span_count_mix(conn, pre_trace_ids),
        _span_count_mix(conn, post_trace_ids),
        threshold=0.20,
    ):
        notes.append("task mix shifted: spans-per-session distribution changed")
    if _mix_shift(
        _tool_mix(conn, pre_trace_ids),
        _tool_mix(conn, post_trace_ids),
        threshold=0.20,
    ):
        notes.append("task mix shifted: tool-call distribution changed")
    if _mix_shift(
        _parser_version_mix(conn, pre_trace_ids),
        _parser_version_mix(conn, post_trace_ids),
    ):
        notes.append("agent/schema version changed: parser-version distribution shifted")
    return notes


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


def _sample_std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = sum(xs) / len(xs)
    variance = sum((value - mean) ** 2 for value in xs) / (len(xs) - 1)
    return math.sqrt(max(variance, 0.0))


def anytime_valid_radius(
    n: float,
    sigma: float,
    *,
    alpha: float = DEFAULT_ALPHA,
    tau2: float = DEFAULT_TAU2,
) -> float:
    """Always-valid CS half-width for a mean difference (mixture variance tau2)."""
    if n <= 0:
        return float("inf")
    sigma = max(abs(sigma), 1e-9)
    numer = 2.0 * (n * tau2 + sigma * sigma)
    denom = n * n * tau2
    log_term = math.log(math.sqrt(n * tau2 + sigma * sigma) / (alpha * sigma))
    return sigma * math.sqrt((numer / denom) * log_term)


def anytime_valid_verdict(
    effect: float,
    se: float,
    *,
    n: float,
    baseline: float,
    min_n: int = 5,
    alpha: float = DEFAULT_ALPHA,
    tau2: float = DEFAULT_TAU2,
    practical_delta_pct: float = DEFAULT_PRACTICAL_DELTA_PCT,
) -> CausalResult:
    """Verdict from anytime-valid CS; practical band is delta fraction of baseline."""
    notes: list[str] = []
    if n < min_n:
        return CausalResult(
            effect_estimate=effect if n else None,
            effect_ci_low=None,
            effect_ci_high=None,
            verdict="inconclusive",
            test_method="anytime_valid_cs",
            confound_flag=False,
            data_notes=[f"n_effective={n:.2f} < {min_n}: inconclusive"],
        )
    if se <= 0:
        se = abs(effect) * 0.1 or 1.0
        notes.append("se estimated from effect magnitude")
    radius = anytime_valid_radius(n, se, alpha=alpha, tau2=tau2)
    ci_lo = effect - radius
    ci_hi = effect + radius
    delta = abs(baseline) * practical_delta_pct if baseline else practical_delta_pct
    if ci_hi < -delta:
        verdict = "improved"
    elif ci_lo > delta:
        verdict = "regressed"
    elif ci_lo >= -delta and ci_hi <= delta:
        verdict = "no_effect"
    else:
        verdict = "inconclusive"
    return CausalResult(
        effect_estimate=round(effect, 4),
        effect_ci_low=round(ci_lo, 4),
        effect_ci_high=round(ci_hi, 4),
        verdict=verdict,
        test_method="anytime_valid_cs",
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
    effective_n: float | None = None,
) -> CausalResult:
    """Compare independent pre/post means with an anytime-valid confidence sequence.

    Sessions are not paired across windows. The point estimate is ``mean(post) -
    mean(pre)`` and the confidence-sequence scale is the root-sum-square of the two
    windows' sample standard deviations. The sequence uses the smaller window size,
    which is conservative when the windows differ. No CUPED covariate is constructed.
    """
    pre_out = [metric_fn(tid) for tid in pre_trace_ids]
    post_out = [metric_fn(tid) for tid in post_trace_ids]

    confound_notes = _confound_notes(conn, pre_trace_ids, post_trace_ids)
    if confound_notes:
        return CausalResult(
            effect_estimate=None,
            effect_ci_low=None,
            effect_ci_high=None,
            verdict="confounded",
            test_method="difference_in_means+anytime_valid_cs",
            confound_flag=True,
            data_notes=confound_notes,
        )

    if not pre_out or not post_out:
        return CausalResult(
            effect_estimate=None,
            effect_ci_low=None,
            effect_ci_high=None,
            verdict="inconclusive",
            test_method="difference_in_means+anytime_valid_cs",
            confound_flag=False,
            data_notes=["both pre and post windows require at least one session"],
        )

    pre_mean = sum(pre_out) / len(pre_out) if pre_out else 0.0
    post_mean = sum(post_out) / len(post_out)
    effect = post_mean - pre_mean
    uncertainty_scale = math.hypot(_sample_std(pre_out), _sample_std(post_out))
    raw_n = min(len(pre_out), len(post_out))
    analysis_n = min(float(raw_n), effective_n) if effective_n is not None else float(raw_n)
    result = anytime_valid_verdict(
        effect,
        uncertainty_scale,
        n=analysis_n,
        baseline=pre_mean,
    )
    result.test_method = "difference_in_means+anytime_valid_cs"
    if effective_n is not None:
        result.data_notes.append(f"clustered effective n={analysis_n:.2f} (raw n={raw_n})")
    return result
