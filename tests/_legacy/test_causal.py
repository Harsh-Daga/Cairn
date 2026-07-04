"""Phase C — causal measurement tests."""

from __future__ import annotations

from cairn.optimize.causal import cuped_adjust, measure_causal_effect, sequential_verdict


def test_cuped_reduces_variance() -> None:
    outcomes = [10.0, 12.0, 11.0, 13.0, 9.0]
    cov = [100.0, 102.0, 101.0, 103.0, 99.0]
    adj, se = cuped_adjust(outcomes, cov)
    assert se >= 0
    assert 9.0 <= adj <= 13.0


def test_sequential_improved_when_ci_below_zero() -> None:
    res = sequential_verdict(-0.5, 0.1, n=10)
    assert res.verdict == "improved"
    assert res.effect_ci_high is not None and res.effect_ci_high < 0


def test_sequential_inconclusive_small_n() -> None:
    res = sequential_verdict(0.1, 0.05, n=2)
    assert res.verdict == "inconclusive"


def test_confounded_on_model_mix_shift(tmp_path) -> None:
    import sqlite3

    from cairn.ledger.schema import migrate

    conn = sqlite3.connect(tmp_path / "c.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO runs (run_id, source, model, started_at) "
        "VALUES ('r1','claude-code','m1','2026-01-01')"
    )
    conn.execute(
        "INSERT INTO runs (run_id, source, model, started_at) "
        "VALUES ('r2','claude-code','m2','2026-01-02')"
    )
    conn.commit()

    def metric(rid: str) -> float:
        return 0.1 if rid == "r1" else 0.2

    res = measure_causal_effect(conn, pre_run_ids=["r1"], post_run_ids=["r2"], metric_fn=metric)
    assert res.verdict == "confounded"
    conn.close()
