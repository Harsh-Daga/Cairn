"""Pillar 2 — behavioral fingerprinting + AMDM drift (Part 10 + §2.7A)."""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np

from cairn.metrics.waste import compute_waste

VECTOR_DIM = 24  # 22 computed dims + 2 zero-pad
_COMPUTED_DIM = 22

FINGERPRINT_AXIS_LABELS = [
    "read",
    "edit",
    "bash",
    "search",
    "delete",
    "sub_agent",
    "read/write",
    "explore/exec",
    "retry",
    "error",
    "identical",
    "ctx mean",
    "ctx max",
    "ctx slope",
    "ctx final",
    "turns",
    "entropy",
    "reasoning",
    "avg tokens",
    "out/in",
    "duration",
    "sub count",
]

# χ² critical values at p=0.99 for df 1..8.
_CHI2_99 = {1: 6.635, 2: 9.210, 3: 11.345, 4: 13.277, 5: 15.086, 6: 16.812, 7: 18.475, 8: 20.090}

_DEFAULT_WINDOW = 200_000


@dataclass
class FingerprintResult:
    vector: list[float]
    read_write_ratio: float
    exploration_ratio: float
    retry_rate: float
    context_fill_traj: list[float]
    turn_count: int
    tool_entropy: float
    week: str | None
    data_notes: list[str] = field(default_factory=list)


def fingerprint_session(
    events: list[dict[str, Any]],
    *,
    started_at: str | None = None,
    ended_at: str | None = None,
    context_window: int | None = None,
    reasoning_tokens: int = 0,
    total_input_tokens: int = 0,
    total_output_tokens: int = 0,
) -> FingerprintResult:
    """Compute the 24-dim behavioral fingerprint for a session."""
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    tool_call_count = len(tool_calls)
    norm_counts: dict[str, int] = defaultdict(int)
    for e in tool_calls:
        n = e.get("tool_norm_name")
        if n:
            norm_counts[str(n)] += 1

    # Dims 0-5: tool mix counts normalized.
    mix_order = ("read", "edit", "bash", "search", "delete", "sub_agent")
    base = max(1, tool_call_count)
    mix = [norm_counts.get(t, 0) / base for t in mix_order]

    read_c = norm_counts.get("read", 0)
    write_c = norm_counts.get("edit", 0) + norm_counts.get("delete", 0)
    explore_c = norm_counts.get("read", 0) + norm_counts.get("search", 0)
    exec_c = norm_counts.get("edit", 0) + norm_counts.get("delete", 0) + norm_counts.get("bash", 0)

    # Dim 6: read:write ratio (clamped to 0..1 via /10).
    rw_ratio = read_c / max(1, write_c)
    # Dim 7: exploration:execution ratio.
    ee_ratio = explore_c / max(1, exec_c)

    # Waste-derived rates (dims 8, 10). Use a no-cost pass for structural counts.
    waste = compute_waste(events, has_cost=False, peak_context_pct=None)
    retry_tokens = sum(1 for _, cat, _ in waste.tags if cat in ("retry_loop", "blind_retry"))
    identical_tokens = sum(1 for _, cat, _ in waste.tags if cat == "identical_call")
    retry_rate = retry_tokens / base
    identical_rate = identical_tokens / base

    # Dim 9: tool error rate.
    error_count = sum(1 for e in tool_calls if e.get("tool_is_error"))
    error_rate = error_count / base

    # Dims 11-14: context-fill trajectory (mean, max, slope, final), in pct.
    window = context_window or _DEFAULT_WINDOW
    ctx_pct = _context_trajectory(events, window)
    if ctx_pct:
        mean_ctx = float(np.mean(ctx_pct))
        max_ctx = float(max(ctx_pct))
        slope = _linear_slope(ctx_pct)
        final_ctx = float(ctx_pct[-1])
    else:
        mean_ctx = max_ctx = slope = final_ctx = 0.0

    # Dim 15: turn count log-scaled.
    turn_count = _count_turns(events)
    turn_log = math.log2(turn_count + 1) / 10.0

    # Dim 16: tool entropy Shannon normalized.
    tool_entropy = _shannon_entropy(list(norm_counts.values()))

    # Dim 17: reasoning depth.
    total_tok = total_input_tokens + total_output_tokens
    reasoning_depth = reasoning_tokens / max(1, total_tok)

    # Dim 18: avg tokens/turn.
    avg_tokens_turn = total_tok / max(1, turn_count)
    avg_norm = min(1.0, avg_tokens_turn / 10_000.0)

    # Dim 19: output:input ratio.
    out_in_ratio = total_output_tokens / max(1, total_input_tokens)
    out_in_norm = min(1.0, out_in_ratio / 4.0)

    # Dim 20: session duration bucket.
    dur_bucket = _duration_bucket(started_at, ended_at)

    # Dim 21: subagent spawn count (log-scaled).
    sub_count = norm_counts.get("sub_agent", 0)
    sub_log = math.log2(sub_count + 1) / 4.0

    computed = [
        *_clamp(mix, 1.0),
        min(1.0, rw_ratio / 10.0),
        min(1.0, ee_ratio / 10.0),
        min(1.0, retry_rate),
        min(1.0, error_rate),
        min(1.0, identical_rate),
        min(1.0, mean_ctx / 100.0),
        min(1.0, max_ctx / 100.0),
        _clamp_slope(slope),
        min(1.0, final_ctx / 100.0),
        min(1.0, turn_log),
        min(1.0, tool_entropy),
        min(1.0, reasoning_depth),
        avg_norm,
        out_in_norm,
        dur_bucket / 2.0,
        min(1.0, sub_log),
    ]
    # Zero-pad to fixed D.
    vector = computed + [0.0] * (VECTOR_DIM - len(computed))

    week = _iso_week(started_at) if started_at else None
    notes: list[str] = []
    if tool_call_count == 0:
        notes.append("no tool calls: fingerprint is all-zero (vector still emitted)")
    if not ctx_pct:
        notes.append("no context_tokens_after: trajectory dims are 0")

    return FingerprintResult(
        vector=vector,
        read_write_ratio=round(rw_ratio, 4),
        exploration_ratio=round(ee_ratio, 4),
        retry_rate=round(retry_rate, 4),
        context_fill_traj=[round(x, 2) for x in ctx_pct],
        turn_count=turn_count,
        tool_entropy=round(tool_entropy, 4),
        week=week,
        data_notes=notes,
    )


# ---------------------------------------------------------------------------
# AMDM drift detection
# ---------------------------------------------------------------------------


@dataclass
class DriftResult:
    drift: bool
    d_squared: float | None
    threshold: float | None
    d_eff: int
    per_dim_deltas: list[float]
    distance: float | None
    kind: str  # "joint_shock", "none", "insufficient_baseline"
    data_notes: list[str] = field(default_factory=list)


def pca_reduce(
    baseline: list[list[float]], *, d_eff: int | None = None
) -> tuple[np.ndarray, np.ndarray, int]:
    """Return (mean, components, d_eff) for PCA on baseline vectors.

    ``components`` is shape ``(d_eff, D)``; projecting ``x`` is ``(x-mean) @ components.T``.
    """
    X = np.array(baseline, dtype=float)
    if X.ndim != 2 or X.shape[0] < 2:
        return np.zeros(VECTOR_DIM), np.zeros((0, VECTOR_DIM)), 0
    mean = X.mean(axis=0)
    Xc = X - mean
    # SVD on the data matrix (n x D). Components from right singular vectors.
    # Use economy SVD.
    try:
        _, _, Vt = np.linalg.svd(Xc, full_matrices=False)
    except np.linalg.LinAlgError:
        return mean, np.zeros((0, VECTOR_DIM)), 0
    max_d = min(8, max(3, X.shape[0] - 1, 3))
    max_d = min(max_d, Vt.shape[0])
    if d_eff is not None:
        max_d = min(max_d, max(3, d_eff))
    max_d = max(3, min(8, max_d))
    if max_d > Vt.shape[0]:
        max_d = Vt.shape[0]
    components = Vt[:max_d]
    return mean, components, max_d


def mahalanobis_distance(x: np.ndarray, mean: np.ndarray, cov_inv: np.ndarray) -> float:
    diff = (x - mean).reshape(-1, 1)
    if cov_inv.size == 0:
        return 0.0
    val = diff.T @ cov_inv @ diff
    return float(np.asarray(val).ravel()[0])


def detect_drift(current: list[float], baseline: list[list[float]]) -> DriftResult:
    """Joint-shock drift: Mahalanobis D² on PCA-reduced dims vs χ²_{d_eff,0.99}."""
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
    X = np.array(baseline, dtype=float)
    Xred = (X - mean_full) @ components.T
    cov = np.cov(Xred, rowvar=False)
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
    x_red = (np.array(current, dtype=float) - mean_full) @ components.T
    d2 = mahalanobis_distance(x_red, np.zeros(d_eff), cov_inv)
    threshold = _CHI2_99.get(d_eff, 20.090)
    # Per-dimension deltas in reduced space (z-scores).
    std = np.sqrt(np.clip(np.diag(cov), 1e-9, None))
    per_dim = [float(v) for v in (x_red / std).tolist()]
    drift = d2 > threshold
    return DriftResult(
        drift=drift,
        d_squared=round(d2, 4),
        threshold=float(threshold),
        d_eff=d_eff,
        per_dim_deltas=[round(z, 3) for z in per_dim],
        distance=round(math.sqrt(max(0.0, d2)), 4),
        kind="joint_shock" if drift else "none",
    )


def detect_gradual_drift(weekly_means: list[tuple[str, list[float]]]) -> dict[str, Any]:
    """Per-axis EWMA with adaptive 3σ bounds; ``DRIFT_GRADUAL`` when an axis
    stays outside bounds >=2 consecutive weeks.

    ``weekly_means`` is a chronologically sorted list of ``(week, vector)``.

    The bound is anchored on an early baseline period (first third of weeks):
    ``baseline_mean ± 3·baseline_std``. Each week's EWMA is tracked; a week is
    "outside" when its EWMA crosses the bound. A sustained shift (>=2 trailing
    weeks outside) emits ``DRIFT_GRADUAL``.
    """
    if len(weekly_means) < 3:
        return {
            "drift": False,
            "axes": [],
            "data_notes": ["need >=3 weekly means for gradual drift"],
        }
    V = np.array([v for _, v in weekly_means], dtype=float)
    [w for w, _ in weekly_means]
    n = V.shape[0]
    anchor_n = max(2, n // 3)
    anchor = V[:anchor_n]
    anchor_mean = anchor.mean(axis=0)
    anchor_std = np.clip(anchor.std(axis=0), 1e-6, None)
    lower = anchor_mean - 3 * anchor_std
    upper = anchor_mean + 3 * anchor_std

    drifting_axes: list[dict[str, Any]] = []
    for axis in range(V.shape[1]):
        series = V[:, axis]
        alpha = 0.4
        ewma = float(series[0])
        ewma_path = [ewma]
        for val in series[1:]:
            ewma = alpha * float(val) + (1 - alpha) * ewma
            ewma_path.append(ewma)
        outside = [not (lower[axis] <= e <= upper[axis]) for e in ewma_path]
        streak = 0
        for o in reversed(outside):
            if o:
                streak += 1
            else:
                break
        if streak >= 2:
            label = (
                FINGERPRINT_AXIS_LABELS[axis]
                if 0 <= axis < len(FINGERPRINT_AXIS_LABELS)
                else f"axis {axis}"
            )
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
    """Scalar Mahalanobis distance (the optimize-loop outcome metric)."""
    res = detect_drift(current, baseline)
    return res.distance


# ---------------------------------------------------------------------------
# Ledger integration
# ---------------------------------------------------------------------------


def backfill_fingerprint(
    writer: Any, run_id: str, *, events: list[dict[str, Any]] | None = None
) -> None:
    """Compute + store the fingerprint for a run and update its weekly baseline."""
    conn = writer.connection
    if events is None:
        events = writer.load_events(run_id)
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        return
    fp = fingerprint_session(
        events,
        started_at=run["started_at"],
        ended_at=run["ended_at"],
        context_window=run["context_window"],
        reasoning_tokens=int(run["reasoning_tokens"] or 0),
        total_input_tokens=int(run["total_input_tokens"] or 0),
        total_output_tokens=int(run["total_output_tokens"] or 0),
    )
    writer.write_fingerprint(
        run_id,
        project=run["project"],
        model=run["model"],
        source=run["source"],
        ts=run["started_at"],
        vector=fp.vector,
        read_write_ratio=fp.read_write_ratio,
        exploration_ratio=fp.exploration_ratio,
        retry_rate=fp.retry_rate,
        context_fill_traj=fp.context_fill_traj,
        turn_count=fp.turn_count,
        tool_entropy=fp.tool_entropy,
        week=fp.week,
    )
    _update_baseline(writer, str(run["project"] or ""), str(run["model"] or ""), fp.week)


def _update_baseline(writer: Any, project: str, model: str, week: str | None) -> None:
    if week is None:
        return
    conn = writer.connection
    rows = conn.execute(
        "SELECT vector_json FROM fingerprints WHERE project = ? AND model = ? AND week = ?",
        (project, model, week),
    ).fetchall()
    vectors = [json.loads(r["vector_json"]) for r in rows if r["vector_json"]]
    if not vectors:
        return
    mean_full, components, d_eff = pca_reduce(vectors)
    if d_eff < 3:
        # Store mean + identity-ish cov_inv so the baseline still records n.
        packed = {"d_eff": 0, "components": [], "cov_inv": [[0.0]]}
    else:
        X = np.array(vectors, dtype=float)
        Xred = (X - mean_full) @ components.T
        cov = np.cov(Xred, rowvar=False)
        cov_inv_arr = np.linalg.pinv(cov)
        packed = {
            "d_eff": d_eff,
            "components": components.tolist(),
            "cov_inv": cov_inv_arr.tolist(),
        }
    writer.write_fingerprint_baseline(
        project=project,
        model=model,
        week=week,
        mean_vector=mean_full.tolist(),
        cov_inv=(
            packed["cov_inv"]
            if not isinstance(packed["cov_inv"], list)
            else packed["cov_inv"]
        ),
        n=len(vectors),
    )
    # Persist the full packed baseline (components + d_eff) inside cov_inv_json.
    conn.execute(
        "UPDATE fingerprint_baselines SET cov_inv_json = ? "
        "WHERE project = ? AND model = ? AND week = ?",
        (json.dumps(packed), project, model, week),
    )
    conn.commit()


def _baseline_vectors_for(
    conn: Any, project: str, model: str, *, before_week: str | None = None
) -> list[list[float]]:
    """Raw fingerprint vectors for a project/model, optionally excluding a week."""
    if before_week is not None:
        rows = conn.execute(
            "SELECT vector_json, week FROM fingerprints "
            "WHERE project = ? AND model = ? AND week < ?",
            (project, model, before_week),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT vector_json FROM fingerprints WHERE project = ? AND model = ?",
            (project, model),
        ).fetchall()
    out = []
    for r in rows:
        try:
            v = json.loads(r["vector_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(v, list):
            out.append([float(x) for x in v])
    return out


# ---------------------------------------------------------------------------
# API payload
# ---------------------------------------------------------------------------


def behavior_payload(conn: Any, *, days: int = 30, project: str | None = None) -> dict[str, Any]:
    """``GET /api/behavior`` — fingerprints + drift + radar (current vs baseline)."""
    where = "WHERE started_at >= date('now', ?)"
    params: list[Any] = [f"-{days} days"]
    if project:
        where += " AND project = ?"
        params.append(project)
    runs = conn.execute(
        f"SELECT run_id, source, project, model, started_at FROM runs {where} "
        "ORDER BY started_at DESC",
        params,
    ).fetchall()

    fingerprints: list[dict[str, Any]] = []
    drift_signals: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    has_any = False
    for r in runs:
        fp_row = conn.execute(
            "SELECT * FROM fingerprints WHERE run_id = ?", (r["run_id"],)
        ).fetchone()
        if fp_row is None:
            continue
        has_any = True
        vec = json.loads(fp_row["vector_json"]) if fp_row["vector_json"] else []
        fingerprints.append(
            {
                "run_id": r["run_id"],
                "project": fp_row["project"],
                "model": fp_row["model"],
                "week": fp_row["week"],
                "read_write_ratio": fp_row["read_write_ratio"],
                "exploration_ratio": fp_row["exploration_ratio"],
                "retry_rate": fp_row["retry_rate"],
                "turn_count": fp_row["turn_count"],
                "tool_entropy": fp_row["tool_entropy"],
            }
        )
        # Drift vs prior weeks' baseline.
        baseline = _baseline_vectors_for(
            conn,
            str(fp_row["project"] or ""),
            str(fp_row["model"] or ""),
            before_week=fp_row["week"],
        )
        if len(baseline) >= 4:
            res = detect_drift(vec, baseline)
            if res.drift:
                drift_signals.append(
                    {
                        "run_id": r["run_id"],
                        "started_at": r["started_at"],
                        "source": r["source"],
                        "model": r["model"],
                        "kind": res.kind,
                        "d_squared": res.d_squared,
                        "threshold": res.threshold,
                        "d_eff": res.d_eff,
                        "distance": res.distance,
                        "per_dim_deltas": res.per_dim_deltas,
                    }
                )
            if (
                res.distance is not None
                and res.threshold
                and res.distance > math.sqrt(res.threshold)
            ):
                anomalies.append(
                    {
                        "run_id": r["run_id"],
                        "started_at": r["started_at"],
                        "distance": res.distance,
                    }
                )

    # Gradual drift across weekly means (per project/model).
    gradual: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for r in runs:
        fp_row = conn.execute(
            "SELECT project, model, week, vector_json FROM fingerprints WHERE run_id = ?",
            (r["run_id"],),
        ).fetchone()
        if fp_row is None:
            continue
        key = (str(fp_row["project"] or ""), str(fp_row["model"] or ""))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        weekly = conn.execute(
            "SELECT week, vector_json FROM fingerprints WHERE project = ? AND model = ? "
            "ORDER BY week ASC",
            key,
        ).fetchall()
        weekly_means = []
        by_week: dict[str, list[list[float]]] = defaultdict(list)
        for w in weekly:
            try:
                by_week[w["week"]].append(json.loads(w["vector_json"]))
            except (json.JSONDecodeError, TypeError):
                continue
        for w, vecs in sorted(by_week.items()):
            if vecs:
                arr = np.array(vecs, dtype=float)
                weekly_means.append((w, arr.mean(axis=0).tolist()))
        grad = detect_gradual_drift(weekly_means)
        if grad["drift"]:
            gradual.append({"project": key[0], "model": key[1], "axes": grad["axes"]})

    # Radar: current-week mean vs baseline mean for the primary project/model.
    radar = _radar(conn, runs, project)

    data_notes: list[str] = []
    if not has_any:
        data_notes.append("no fingerprints in range")
    if not drift_signals and not gradual:
        data_notes.append("no drift detected")

    if not has_any:
        return {
            "fingerprints": None,
            "drift": None,
            "gradual": None,
            "anomalies": None,
            "radar": None,
            "data_notes": data_notes,
        }
    return {
        "fingerprints": fingerprints,
        "drift": drift_signals,
        "gradual": gradual,
        "anomalies": anomalies,
        "radar": radar,
        "data_notes": data_notes,
    }


def _radar(conn: Any, runs: Any, project: str | None) -> dict[str, Any] | None:
    """Current-week mean vector vs all-time baseline mean for radar plotting."""
    if not runs:
        return None
    # Pick the project/model with the most fingerprints.
    key_row = conn.execute(
        """
        SELECT project, model, COUNT(*) AS n FROM fingerprints
        GROUP BY project, model ORDER BY n DESC LIMIT 1
        """
    ).fetchone()
    if key_row is None:
        return None
    project_v, model_v = str(key_row["project"] or ""), str(key_row["model"] or "")
    current = conn.execute(
        """
        SELECT vector_json FROM fingerprints
        WHERE project = ? AND model = ?
        ORDER BY week DESC LIMIT 5
        """,
        (project_v, model_v),
    ).fetchall()
    baseline = conn.execute(
        "SELECT vector_json FROM fingerprints WHERE project = ? AND model = ?",
        (project_v, model_v),
    ).fetchall()
    if not current or not baseline:
        return None
    cur_vecs = [json.loads(r["vector_json"]) for r in current if r["vector_json"]]
    base_vecs = [json.loads(r["vector_json"]) for r in baseline if r["vector_json"]]
    cur_mean = np.array(cur_vecs, dtype=float).mean(axis=0).tolist()
    base_mean = np.array(base_vecs, dtype=float).mean(axis=0).tolist()
    # Label the 22 computed axes.
    labels = FINGERPRINT_AXIS_LABELS
    return {
        "project": project_v,
        "model": model_v,
        "labels": labels,
        "current_week": [round(x, 4) for x in cur_mean[: len(labels)]],
        "baseline": [round(x, 4) for x in base_mean[: len(labels)]],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clamp(values: list[float], hi: float) -> list[float]:
    return [max(0.0, min(hi, float(v))) for v in values]


def _clamp_slope(slope: float) -> float:
    return max(0.0, min(1.0, (slope + 10.0) / 20.0))


def _context_trajectory(events: list[dict[str, Any]], window: int) -> list[float]:
    pcts: list[float] = []
    for e in events:
        ctx = e.get("context_tokens_after")
        if isinstance(ctx, (int, float)) and int(ctx) > 0 and window > 0:
            pcts.append(round(int(ctx) / window * 100, 2))
    return pcts


def _count_turns(events: list[dict[str, Any]]) -> int:
    n = 0
    for e in events:
        if e.get("type") == "user_prompt":
            n += 1
    return max(1, n)


def _shannon_entropy(counts: list[int]) -> float:
    total = sum(counts)
    if total <= 0:
        return 0.0
    k = len(counts)
    h = 0.0
    for c in counts:
        if c > 0:
            p = c / total
            h -= p * math.log2(p)
    return h / math.log2(max(2, k))


def _duration_bucket(started_at: str | None, ended_at: str | None) -> int:
    if not started_at or not ended_at:
        return 0
    try:
        s = _parse_iso(started_at)
        e = _parse_iso(ended_at)
        if s is None or e is None:
            return 0
        minutes = (e - s).total_seconds() / 60.0
        if minutes < 0:
            return 0
        if minutes < 5:
            return 0
        if minutes < 30:
            return 1
        return 2
    except (ValueError, TypeError):
        return 0


def _parse_iso(ts: str) -> datetime | None:
    from datetime import datetime

    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _iso_week(started_at: str | None) -> str | None:
    if not started_at:
        return None
    day = started_at[:10]
    try:
        y, m, d = (int(x) for x in day.split("-"))
        iso = date(y, m, d).isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    except (ValueError, OSError):
        return None


def _linear_slope(ys: list[float]) -> float:
    n = len(ys)
    if n < 2:
        return 0.0
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
    den = sum((x - mx) ** 2 for x in xs)
    if den == 0:
        return 0.0
    return num / den
