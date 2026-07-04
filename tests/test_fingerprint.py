"""Pillar 2 tests — fingerprint dims + AMDM Mahalanobis + gradual EWMA + baseline."""

from __future__ import annotations

import random

import numpy as np

from cairn.metrics.fingerprint import (
    VECTOR_DIM,
    detect_drift,
    detect_gradual_drift,
    fingerprint_distance,
    fingerprint_session,
    pca_reduce,
)


def _mk(
    reads,
    edits,
    bash=1,
    searches=1,
    retries=0,
    errors=0,
    turns=10,
    dur=("2026-06-01T00:00:00", "2026-06-01T00:20:00"),
    inp=1000,
    out=500,
):
    events: list[dict] = []
    for i in range(turns):
        events.append({"type": "user_prompt", "text_inline": f"q{i}"})
        for _ in range(reads):
            events.append({"type": "tool_call", "tool_norm_name": "read", "path_rel": "a.py"})
        for _ in range(edits):
            events.append({"type": "tool_call", "tool_norm_name": "edit", "path_rel": "a.py"})
        for _ in range(bash):
            events.append({"type": "tool_call", "tool_norm_name": "bash"})
        for _ in range(searches):
            events.append({"type": "tool_call", "tool_norm_name": "search"})
        for _ in range(retries):
            events.append(
                {
                    "type": "tool_call",
                    "tool_norm_name": "read",
                    "args_hash": "h1",
                    "text_hash": "h1",
                    "path_rel": "a.py",
                }
            )
            events.append(
                {
                    "type": "tool_result",
                    "tool_norm_name": "read",
                    "tool_is_error": 1,
                    "path_rel": "a.py",
                }
            )
            events.append(
                {
                    "type": "tool_call",
                    "tool_norm_name": "read",
                    "args_hash": "h1",
                    "text_hash": "h1",
                    "path_rel": "a.py",
                }
            )
        for _ in range(errors):
            events.append({"type": "tool_call", "tool_norm_name": "bash", "tool_is_error": 1})
        events.append(
            {"type": "assistant_message", "text_inline": "a", "context_tokens_after": 50000}
        )
    return fingerprint_session(
        events, started_at=dur[0], ended_at=dur[1], total_input_tokens=inp, total_output_tokens=out
    )


def test_vector_dim_stable_and_zero_padded() -> None:
    fp = _mk(3, 2, 1, 1)
    assert len(fp.vector) == VECTOR_DIM == 24
    # 22 computed dims + 2 zero-pad.
    assert fp.vector[22] == 0.0 and fp.vector[23] == 0.0
    # No NaNs.
    assert all(isinstance(x, float) and x == x for x in fp.vector)


def test_vector_zero_for_no_tool_calls() -> None:
    fp = fingerprint_session(
        [
            {"type": "user_prompt", "text_inline": "q"},
            {"type": "assistant_message", "text_inline": "a"},
        ],
        started_at="2026-06-01T00:00:00",
        ended_at="2026-06-01T00:01:00",
    )
    assert len(fp.vector) == VECTOR_DIM
    assert all(v == 0.0 for v in fp.vector[:6])  # tool mix all zero


def test_amdm_joint_shock_flags_injected_drift() -> None:
    random.seed(1)
    np.random.seed(1)
    baseline = [
        _mk(
            random.randint(2, 4),
            random.randint(1, 3),
            random.randint(0, 2),
            random.randint(0, 2),
            retries=random.randint(0, 1),
            turns=random.randint(8, 14),
        ).vector
        for _ in range(20)
    ]
    outlier = _mk(9, 0, 0, 0, retries=6, turns=14).vector
    res = detect_drift(outlier, baseline)
    assert res.drift, f"expected drift, got D2={res.d_squared} thr={res.threshold}"
    assert res.d_eff >= 3
    assert res.d_squared > res.threshold
    # Per-dim deltas reported.
    assert len(res.per_dim_deltas) == res.d_eff


def test_normal_session_does_not_drift() -> None:
    random.seed(2)
    np.random.seed(2)
    baseline = [_mk(3, 2, 1, 1, turns=10).vector for _ in range(20)]
    # Add small noise so covariance is non-degenerate.
    baseline = [[v + random.gauss(0, 0.01) for v in vec] for vec in baseline]
    normal = _mk(3, 2, 1, 1).vector
    res = detect_drift(normal, baseline)
    assert not res.drift


def test_fingerprint_distance_scalar_computed() -> None:
    random.seed(3)
    np.random.seed(3)
    baseline = [_mk(3, 2, 1, 1, turns=10).vector for _ in range(10)]
    baseline = [[v + random.gauss(0, 0.02) for v in vec] for vec in baseline]
    d = fingerprint_distance(_mk(3, 2, 1, 1).vector, baseline)
    assert d is not None and d >= 0.0


def test_gradual_drift_flags_sustained_shift() -> None:
    weeks = [(f"2026-W{i:02d}", _mk(3, 2, 1, 1).vector) for i in range(1, 4)]
    weeks += [(f"2026-W{i:02d}", _mk(3, 12, 1, 1).vector) for i in range(4, 8)]
    g = detect_gradual_drift(weeks)
    assert g["drift"]
    assert g["axes"]


def test_insufficient_baseline_no_drift() -> None:
    res = detect_drift(_mk(3, 2).vector, [_mk(3, 2).vector])
    assert not res.drift
    assert res.kind == "insufficient_baseline"


def test_pca_reduce_returns_components() -> None:
    random.seed(4)
    np.random.seed(4)
    vecs = [[random.random() for _ in range(VECTOR_DIM)] for _ in range(10)]
    mean, comps, d_eff = pca_reduce(vecs)
    assert d_eff >= 3
    assert comps.shape[0] == d_eff
    assert mean.shape[0] == VECTOR_DIM
