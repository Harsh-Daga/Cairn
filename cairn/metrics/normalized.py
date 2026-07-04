"""Difficulty-normalized metrics and expectation baselines — Phase B."""

from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

MIN_BASELINE_N = 5


@dataclass
class ExpectedMetric:
    mean: float | None
    stdev: float | None
    n: int
    sufficient: bool
    data_notes: list[str]


def update_expectation_baselines(
    conn: sqlite3.Connection,
    *,
    model: str,
    difficulty_bucket: str,
    metric: str,
    value: float,
) -> None:
    """Rolling mean/stdev for one (model, bucket, metric) observation."""
    row = conn.execute(
        """
        SELECT mean, stdev, n FROM expectation_baselines
        WHERE model = ? AND difficulty_bucket = ? AND metric = ?
        """,
        (model, difficulty_bucket, metric),
    ).fetchone()
    if row is None:
        conn.execute(
            """
            INSERT INTO expectation_baselines (
                model, difficulty_bucket, metric, mean, stdev, n, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (model, difficulty_bucket, metric, value, 0.0, datetime.now(UTC).isoformat()),
        )
        return
    n = int(row[2]) + 1
    old_mean = float(row[0] or 0.0)
    new_mean = old_mean + (value - old_mean) / n
    old_stdev = float(row[1] or 0.0)
    if n > 1:
        # Welford-style incremental variance.
        delta = value - old_mean
        delta2 = value - new_mean
        var = ((n - 2) * old_stdev**2 + delta * delta2) / (n - 1)
        new_stdev = math.sqrt(max(var, 0.0))
    else:
        new_stdev = 0.0
    conn.execute(
        """
        UPDATE expectation_baselines
        SET mean = ?, stdev = ?, n = ?, updated_at = ?
        WHERE model = ? AND difficulty_bucket = ? AND metric = ?
        """,
        (new_mean, new_stdev, n, datetime.now(UTC).isoformat(), model, difficulty_bucket, metric),
    )


def get_expected(
    conn: sqlite3.Connection,
    *,
    model: str,
    difficulty_bucket: str,
    metric: str,
) -> ExpectedMetric:
    row = conn.execute(
        """
        SELECT mean, stdev, n FROM expectation_baselines
        WHERE model = ? AND difficulty_bucket = ? AND metric = ?
        """,
        (model, difficulty_bucket, metric),
    ).fetchone()
    if row is None or int(row[2]) < MIN_BASELINE_N:
        n = int(row[2]) if row else 0
        return ExpectedMetric(
            mean=float(row[0]) if row and row[0] is not None else None,
            stdev=float(row[1]) if row and row[1] is not None else None,
            n=n,
            sufficient=False,
            data_notes=[f"insufficient data: n={n} < {MIN_BASELINE_N} for {metric}"],
        )
    return ExpectedMetric(
        mean=float(row[0]),
        stdev=float(row[1] or 0.0),
        n=int(row[2]),
        sufficient=True,
        data_notes=[],
    )


def cost_vs_expected(conn: sqlite3.Connection, run: dict[str, Any]) -> dict[str, Any]:
    """Compare session tokens/cost to difficulty-adjusted expectation band."""
    model = str(run.get("model") or "unknown")
    bucket = str(run.get("difficulty_bucket") or "standard")
    tokens = int(run.get("total_input_tokens") or 0) + int(run.get("total_output_tokens") or 0)
    waste = int(run.get("waste_tokens") or 0)
    exp_tokens = get_expected(conn, model=model, difficulty_bucket=bucket, metric="total_tokens")
    exp_waste = get_expected(conn, model=model, difficulty_bucket=bucket, metric="waste_ratio")

    waste_ratio = waste / tokens if tokens > 0 else None
    ratio_vs_expected: float | None = None
    p95_band: str | None = None
    if exp_tokens.sufficient and exp_tokens.mean and exp_tokens.mean > 0:
        ratio_vs_expected = round(tokens / exp_tokens.mean, 2)
        if exp_tokens.stdev is not None:
            p95 = exp_tokens.mean + 1.645 * exp_tokens.stdev
            p95_band = f"p95≈{p95:.0f} tokens"
    waste_vs_expected: float | None = None
    if exp_waste.sufficient and waste_ratio is not None and exp_waste.mean:
        waste_vs_expected = round(waste_ratio / exp_waste.mean, 2)

    notes = exp_tokens.data_notes + exp_waste.data_notes
    label = None
    if ratio_vs_expected is not None:
        label = f"{ratio_vs_expected:.1f}× expected tokens ({bucket})"
        if p95_band:
            label += f" ({p95_band})"

    return {
        "tokens": tokens,
        "waste_ratio": waste_ratio,
        "ratio_vs_expected": ratio_vs_expected,
        "waste_vs_expected": waste_vs_expected,
        "expected_tokens_mean": exp_tokens.mean,
        "expected_tokens_stdev": exp_tokens.stdev,
        "expected_waste_mean": exp_waste.mean,
        "label": label,
        "data_notes": notes,
    }


def backfill_expectations_for_run(conn: sqlite3.Connection, run: dict[str, Any]) -> None:
    """Record this run's metrics into expectation baselines."""
    model = str(run.get("model") or "unknown")
    bucket = str(run.get("difficulty_bucket") or "standard")
    tokens = float(
        int(run.get("total_input_tokens") or 0) + int(run.get("total_output_tokens") or 0)
    )
    waste = float(int(run.get("waste_tokens") or 0))
    if tokens <= 0:
        return
    update_expectation_baselines(
        conn, model=model, difficulty_bucket=bucket, metric="total_tokens", value=tokens
    )
    update_expectation_baselines(
        conn, model=model, difficulty_bucket=bucket, metric="waste_ratio", value=waste / tokens
    )


def is_runaway_vs_expectation(
    conn: sqlite3.Connection, run: dict[str, Any], *, ratio: float
) -> bool:
    """True when session exceeds expectation band, not merely raw length."""
    cmp_ = cost_vs_expected(conn, run)
    if cmp_["ratio_vs_expected"] is not None and float(cmp_["ratio_vs_expected"]) >= 2.5:
        return True
    # Fallback when baselines insufficient: keep legacy 3× half-ratio gate.
    exp = get_expected(
        conn,
        model=str(run.get("model") or "unknown"),
        difficulty_bucket=str(run.get("difficulty_bucket") or "standard"),
        metric="total_tokens",
    )
    if not exp.sufficient:
        return ratio > 3.0
    return False
