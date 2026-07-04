"""Measure whether applied optimizations helped (§2.7E measured loop)."""

from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cairn.ledger.ledger import Ledger

IMPROVED_DROP = 0.10  # §2.7E: ±10% band (legacy classify)
MIN_POST_SESSIONS = 5
MIN_POST_DAYS = 14

# Measured-loop defaults (§2.7E).
DEFAULT_M = 10  # post-apply sessions required before measuring
DEFAULT_K = 3  # holds before a hard prune is allowed
PRUNE_PROB_THRESHOLD = 0.2

# Beta prior — weak, neutral (mean 0.5).
_ALPHA_PRIOR = 1.0
_BETA_PRIOR = 1.0


@dataclass
class Verdict:
    entry_id: str
    kind: str
    baseline: float
    outcome: float
    verdict: str
    savings_per_week: float


@dataclass
class MeasuredRule:
    opt_id: str
    block_key: str
    kind: str
    applied_at: str
    baseline_metric: float | None
    outcome_metric: float | None
    fingerprint_distance_baseline: float | None
    fingerprint_distance_outcome: float | None
    verdict: str  # improved | no_effect | regressed | insufficient
    proposal_pool: list[str] = field(default_factory=list)
    holdout: list[str] = field(default_factory=list)
    outcome_sessions: int = 0
    reward: float = 0.0
    data_notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Legacy metric helpers (kept for existing tests / prune path)
# ---------------------------------------------------------------------------


def measure_metric(
    conn: sqlite3.Connection,
    kind: str,
    evidence: dict[str, Any],
    *,
    start_day: str,
    end_day: str,
) -> float:
    if kind == "file_guide":
        path = evidence.get("path")
        return _read_count(conn, path, start_day, end_day) if path else 0.0
    if kind in ("command_fix", "known_issue", "rule"):
        name = evidence.get("tool_name") or evidence.get("bad")
        if name:
            return _failure_count(conn, str(name), start_day, end_day)
        if evidence.get("evidence_type") == "context_overflow":
            return _context_overflow_count(conn, start_day, end_day)
        if evidence.get("evidence_type") == "identical_grep":
            return float(evidence.get("searches", 0))
    if kind == "repo_map":
        return _orientation_ratio(conn, start_day, end_day)
    return 0.0


def _read_count(conn: sqlite3.Connection, path: str, start: str, end: str) -> float:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.path_rel = ? AND e.tool_norm_name = 'read'
          AND date(r.started_at) >= date(?) AND date(r.started_at) <= date(?)
        """,
        (path, start, end),
    ).fetchone()
    return float(row["n"] if row else 0)


def _failure_count(conn: sqlite3.Connection, name: str, start: str, end: str) -> float:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM events e
        JOIN runs r ON r.run_id = e.run_id
        WHERE e.tool_is_error = 1 AND e.tool_name = ?
          AND date(r.started_at) >= date(?) AND date(r.started_at) <= date(?)
        """,
        (name, start, end),
    ).fetchone()
    return float(row["n"] if row else 0)


def _context_overflow_count(conn: sqlite3.Connection, start: str, end: str) -> float:
    row = conn.execute(
        """
        SELECT COUNT(*) AS n FROM runs
        WHERE peak_context_pct > 85
          AND date(started_at) >= date(?) AND date(started_at) <= date(?)
        """,
        (start, end),
    ).fetchone()
    return float(row["n"] if row else 0)


def _orientation_ratio(conn: sqlite3.Connection, start: str, end: str) -> float:
    row = conn.execute(
        """
        SELECT SUM(waste_tokens) AS waste, SUM(total_input_tokens) AS inp
        FROM runs
        WHERE date(started_at) >= date(?) AND date(started_at) <= date(?)
        """,
        (start, end),
    ).fetchone()
    if not row or not row["inp"]:
        return 0.0
    return float(row["waste"] or 0) / float(row["inp"])


def classify(baseline: float, outcome: float) -> str:
    """±10% band: improved / neutral / worsened (legacy names)."""
    if baseline <= 0:
        return "worsened" if outcome > 0 else "neutral"
    if outcome <= baseline * (1 - IMPROVED_DROP):
        return "improved"
    if outcome > baseline * (1 + IMPROVED_DROP):
        return "worsened"
    return "neutral"


def verdict_for(
    baseline: float,
    outcome: float,
    fp_baseline: float | None = None,
    fp_outcome: float | None = None,
) -> str:
    """§2.7E verdict: improved | no_effect | regressed.

    ``improved`` requires outcome < baseline*0.9 AND fingerprint distance to
    shrink (when both are available). ``regressed`` if outcome > baseline*1.1
    OR fingerprint distance grows. Otherwise ``no_effect``. div0-guarded.
    """
    if baseline <= 0:
        if outcome <= 0:
            return "no_effect"
        return "regressed"
    improved_metric = outcome < baseline * 0.9
    regressed_metric = outcome > baseline * 1.1
    fp_shrunk = fp_outcome is None or fp_baseline is None or fp_outcome <= fp_baseline
    fp_grew = fp_outcome is not None and fp_baseline is not None and fp_outcome > fp_baseline
    if improved_metric and fp_shrunk:
        return "improved"
    if regressed_metric or fp_grew:
        return "regressed"
    return "no_effect"


def compute_outcomes(ledger: Ledger, *, now_day: str | None = None) -> list[Verdict]:
    conn = ledger.connection
    now_day = now_day or str(conn.execute("SELECT date('now')").fetchone()[0])
    rows = conn.execute(
        """
        SELECT opt_id, block_key, kind, evidence_json, baseline_metric, applied_at
        FROM optimizations WHERE status = 'applied'
        """
    ).fetchall()
    verdicts: list[Verdict] = []
    for r in rows:
        applied_day = str(r["applied_at"] or "")[:10]
        if not applied_day or not _enough_evidence(conn, applied_day, now_day):
            continue
        evidence = _safe_json(r["evidence_json"])
        baseline = float(r["baseline_metric"] or 0)
        outcome = measure_metric(
            conn, str(r["kind"]), evidence, start_day=applied_day, end_day=now_day
        )
        verdict = classify(baseline, outcome)
        conn.execute(
            "UPDATE optimizations SET outcome_metric = ? WHERE opt_id = ?",
            (outcome, r["opt_id"]),
        )
        verdicts.append(
            Verdict(
                entry_id=str(r["block_key"]),
                kind=str(r["kind"]),
                baseline=baseline,
                outcome=outcome,
                verdict=verdict,
                savings_per_week=round(max(0.0, baseline - outcome) * 0.5, 2),
            )
        )
    conn.commit()
    return verdicts


def _enough_evidence(conn: sqlite3.Connection, applied_day: str, now_day: str) -> bool:
    days = conn.execute("SELECT julianday(?) - julianday(?)", (now_day, applied_day)).fetchone()[0]
    if days is not None and days >= MIN_POST_DAYS:
        return True
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM runs WHERE date(started_at) >= date(?)",
        (applied_day,),
    ).fetchone()
    return bool(row and row["n"] >= MIN_POST_SESSIONS)


def print_status(root: Path) -> int:
    db = root / ".cairn" / "ledger.db"
    if not db.is_file():
        print("No ledger yet. Run `cairn sync` first.")
        return 0
    ledger = Ledger(db)
    try:
        compute_outcomes(ledger)
        rows = ledger.connection.execute(
            """
            SELECT block_key, kind, status, applied_at, baseline_metric, outcome_metric,
                   fingerprint_distance_baseline, fingerprint_distance_outcome
            FROM optimizations WHERE status IN ('applied', 'pending', 'reverted', 'pruned')
            ORDER BY applied_at DESC
            """
        ).fetchall()
    finally:
        ledger.close()

    if not rows:
        print("No applied optimizations yet. Run `cairn optimize --apply`.")
        return 0

    print("Optimization status:")
    for r in rows:
        applied = str(r["applied_at"] or "")[:10] or "-"
        ba = "-" if r["baseline_metric"] is None else f"{r['baseline_metric']:g}"
        oa = "-" if r["outcome_metric"] is None else f"{r['outcome_metric']:g}"
        fpb = (
            "-"
            if r["fingerprint_distance_baseline"] is None
            else f"{r['fingerprint_distance_baseline']:g}"
        )
        fpo = (
            "-"
            if r["fingerprint_distance_outcome"] is None
            else f"{r['fingerprint_distance_outcome']:g}"
        )
        print(
            f"  [{r['status']}] {r['kind']}/{r['block_key']}  applied {applied}  "
            f"{ba} -> {oa}  fp {fpb} -> {fpo}"
        )
    return 0


def _safe_json(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


# ---------------------------------------------------------------------------
# Holdout measurement (§2.7E)
# ---------------------------------------------------------------------------


def _run_ids_in_window(conn: sqlite3.Connection, start: str, end: str) -> list[str]:
    rows = conn.execute(
        "SELECT run_id FROM runs "
        "WHERE date(started_at) >= date(?) AND date(started_at) <= date(?) "
        "ORDER BY started_at ASC",
        (start, end),
    ).fetchall()
    return [str(r["run_id"]) for r in rows]


def _run_ids_between(conn: sqlite3.Connection, start_iso: str, end_iso: str) -> list[str]:
    """Run ids with ``start_iso <= started_at < end_iso`` (strict upper bound)."""
    rows = conn.execute(
        "SELECT run_id FROM runs WHERE started_at >= ? AND started_at < ? ORDER BY started_at ASC",
        (start_iso, end_iso),
    ).fetchall()
    return [str(r["run_id"]) for r in rows]


def _post_apply_runs(conn: sqlite3.Connection, applied_at: str) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT run_id, project, model, started_at FROM runs "
        "WHERE started_at > ? ORDER BY started_at ASC",
        (applied_at,),
    ).fetchall()


def _fingerprint_distance_for_runs(conn: sqlite3.Connection, run_ids: list[str]) -> float | None:
    if not run_ids:
        return None
    try:
        from cairn.metrics.fingerprint import _baseline_vectors_for, detect_drift
    except Exception:
        return None
    distances: list[float] = []
    for rid in run_ids:
        row = conn.execute(
            "SELECT vector_json, project, model, week FROM fingerprints WHERE run_id = ?",
            (rid,),
        ).fetchone()
        if row is None or not row["vector_json"]:
            continue
        try:
            vec = json.loads(row["vector_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        baseline = _baseline_vectors_for(
            conn, str(row["project"] or ""), str(row["model"] or ""), before_week=row["week"]
        )
        if len(baseline) < 4:
            continue
        res = detect_drift(vec, baseline)
        if res.distance is not None:
            distances.append(res.distance)
    if not distances:
        return None
    return round(sum(distances) / len(distances), 4)


def _quality_mean_for_runs(conn: sqlite3.Connection, run_ids: list[str]) -> float | None:
    if not run_ids:
        return None
    placeholders = ",".join("?" * len(run_ids))
    row = conn.execute(
        f"SELECT AVG(o.quality_score) AS m FROM outcomes o "
        f"WHERE o.run_id IN ({placeholders}) AND o.quality_score IS NOT NULL",
        run_ids,
    ).fetchone()
    if not row or row["m"] is None:
        return None
    return round(float(row["m"]), 2)


def measure_rule(
    conn: sqlite3.Connection,
    opt_row: sqlite3.Row,
    *,
    m: int = DEFAULT_M,
    now_day: str | None = None,
) -> MeasuredRule:
    """Measure a single applied rule on the holdout (post-apply sessions)."""
    applied_at = str(opt_row["applied_at"] or "")
    notes: list[str] = []
    pool: list[str] = []
    holdout: list[str] = []
    if applied_at:
        from datetime import datetime as _dt
        from datetime import timedelta

        try:
            ad = _dt.fromisoformat(applied_at)
            pool_start_iso = (ad - timedelta(days=14)).isoformat()
            pool = _run_ids_between(conn, pool_start_iso, applied_at)
        except ValueError:
            notes.append("unparseable applied_at; pool window unavailable")
        post = _post_apply_runs(conn, applied_at)
        # Holdout = post-apply sessions the proposer never saw. The pool is
        # strictly before applied_at and the holdout strictly after, so the
        # two sets are disjoint by construction (the proposer never sees the
        # measurement window).
        holdout = [str(r["run_id"]) for r in post][: max(m, 0)]
    else:
        notes.append("no applied_at; cannot split holdout")

    # Safety net: should never trigger given the strict < / > split above.
    overlap = set(pool) & set(holdout)
    if overlap:
        holdout = [r for r in holdout if r not in pool]
        notes.append("pool/holdout overlap detected and removed")

    if len(holdout) < m:
        return MeasuredRule(
            opt_id=str(opt_row["opt_id"]),
            block_key=str(opt_row["block_key"]),
            kind=str(opt_row["kind"]),
            applied_at=applied_at,
            baseline_metric=_float(opt_row["baseline_metric"]),
            outcome_metric=None,
            fingerprint_distance_baseline=_float(opt_row["fingerprint_distance_baseline"]),
            fingerprint_distance_outcome=None,
            verdict="insufficient",
            proposal_pool=pool,
            holdout=holdout,
            outcome_sessions=len(holdout),
            reward=0.0,
            data_notes=notes + [f"holdout has {len(holdout)} sessions; need >= {m} to measure"],
        )

    evidence = _safe_json(opt_row["evidence_json"])
    baseline = _float(opt_row["baseline_metric"]) or 0.0
    now_day = now_day or str(conn.execute("SELECT date('now')").fetchone()[0])
    outcome = measure_metric(
        conn,
        str(opt_row["kind"]),
        evidence,
        start_day=applied_at[:10] or now_day,
        end_day=now_day,
    )
    fp_baseline = _float(opt_row["fingerprint_distance_baseline"])
    fp_outcome = _fingerprint_distance_for_runs(conn, holdout)

    # Synthetic holdout contrast when there are >=20 post-apply sessions.
    contrast_note = None
    if len(holdout) >= 20:
        contrast_note = _synthetic_holdout_contrast(conn, opt_row, holdout)
        if contrast_note:
            notes.append(contrast_note)

    verdict = verdict_for(baseline, outcome, fp_baseline, fp_outcome)
    reward = _composite_reward(baseline, outcome, fp_baseline, fp_outcome)

    # Phase C: CUPED + sequential test when holdout is large enough.
    causal_effect: Any = None
    if len(pool) >= 3 and len(holdout) >= 3:
        from cairn.optimize.causal import measure_causal_effect

        def _run_waste_ratio(rid: str) -> float:
            row = conn.execute(
                "SELECT waste_tokens, total_input_tokens FROM runs WHERE run_id = ?",
                (rid,),
            ).fetchone()
            if row is None or not row["total_input_tokens"]:
                return 0.0
            return float(row["waste_tokens"] or 0) / float(row["total_input_tokens"])

        causal = measure_causal_effect(
            conn, pre_run_ids=pool, post_run_ids=holdout, metric_fn=_run_waste_ratio
        )
        causal_effect = causal
        if causal.verdict in ("improved", "regressed", "confounded", "inconclusive", "no_effect"):
            verdict = (
                "insufficient"
                if causal.verdict == "inconclusive"
                else ("no_effect" if causal.verdict == "no_effect" else causal.verdict)
            )
        notes.extend(causal.data_notes)

    res = MeasuredRule(
        opt_id=str(opt_row["opt_id"]),
        block_key=str(opt_row["block_key"]),
        kind=str(opt_row["kind"]),
        applied_at=applied_at,
        baseline_metric=baseline,
        outcome_metric=round(outcome, 4),
        fingerprint_distance_baseline=fp_baseline,
        fingerprint_distance_outcome=fp_outcome,
        verdict=verdict,
        proposal_pool=pool,
        holdout=holdout,
        outcome_sessions=len(holdout),
        reward=reward,
        data_notes=notes,
    )
    res._causal = causal_effect  # type: ignore[attr-defined]
    return res


def _synthetic_holdout_contrast(
    conn: sqlite3.Connection, opt_row: sqlite3.Row, holdout: list[str]
) -> str | None:
    """Best-effort rule-active vs synthetic-holdout (different project) contrast."""
    project_row = conn.execute(
        "SELECT project FROM runs WHERE run_id = ?", (holdout[0],)
    ).fetchone()
    if project_row is None:
        return None
    primary_project = str(project_row["project"] or "")
    if not primary_project:
        return None
    applied_at = str(opt_row["applied_at"] or "")
    synth = conn.execute(
        "SELECT run_id FROM runs WHERE started_at > ? AND project != ? "
        "AND project IS NOT NULL LIMIT 50",
        (applied_at, primary_project),
    ).fetchall()
    if len(synth) < 5:
        return None
    return (
        f"contrast: {len(holdout)} rule-active vs {len(synth)} synthetic-holdout "
        f"(different project) sessions; contrast is best-effort"
    )


def _composite_reward(
    baseline: float,
    outcome: float,
    fp_baseline: float | None,
    fp_outcome: float | None,
) -> float:
    """Reward in [0,1]: waste-down (0.6) + fingerprint stability (0.4)."""
    if baseline > 0:
        waste_improved = max(0.0, min(1.0, (baseline - outcome) / baseline))
    else:
        waste_improved = 0.0 if outcome > 0 else 1.0
    if fp_baseline is not None and fp_outcome is not None:
        if fp_baseline > 0:
            fp_stable = max(0.0, min(1.0, (fp_baseline - fp_outcome) / fp_baseline))
        else:
            fp_stable = 1.0 if fp_outcome <= 0 else 0.0
    else:
        fp_stable = 0.5  # neutral when unavailable
    return round(0.6 * waste_improved + 0.4 * fp_stable, 4)


def _float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Thompson-sampling multi-armed bandit (§2.7E)
# ---------------------------------------------------------------------------


class Bandit:
    """Beta-Bernoulli bandit over managed rules (arms).

    Each arm stores ``alpha``/``beta`` (Beta posterior on P(rule improves the
    metric)). ``sample()`` draws a Thompson sample for selection; ``update()``
    folds in a [0,1] reward. ``prune()`` returns arms to drop after ``K`` holds
    with posterior P(improve) < threshold.
    """

    def __init__(self, arms: dict[str, tuple[float, float]] | None = None) -> None:
        self.arms: dict[str, list[float]] = {
            arm: [float(a), float(b)] for arm, (a, b) in (arms or {}).items()
        }
        self.holds: dict[str, int] = {arm: 0 for arm in self.arms}
        self._rng = random.Random()

    def ensure(self, arm: str) -> None:
        if arm not in self.arms:
            self.arms[arm] = [_ALPHA_PRIOR, _BETA_PRIOR]
            self.holds[arm] = 0

    def sample(self, arm: str) -> float:
        """Thompson sample of P(improve) for ``arm`` (Beta(alpha, beta))."""
        self.ensure(arm)
        a, b = self.arms[arm]
        return float(self._rng.betavariate(max(a, 1e-3), max(b, 1e-3)))

    def select(self, candidates: list[str]) -> str | None:
        """Thompson-sampling selection across candidate arms."""
        if not candidates:
            return None
        best: str | None = None
        best_draw = -1.0
        for arm in candidates:
            draw = self.sample(arm)
            if draw > best_draw:
                best_draw = draw
                best = arm
        return best

    def update(self, arm: str, reward: float) -> None:
        """Fold a [0,1] reward into the Beta posterior."""
        self.ensure(arm)
        reward = max(0.0, min(1.0, float(reward)))
        # Beta-Bernoulli conjugate update with a fractional reward.
        self.arms[arm][0] += reward
        self.arms[arm][1] += 1.0 - reward
        self.holds[arm] = self.holds.get(arm, 0) + 1

    def p_improve(self, arm: str) -> float:
        """Posterior mean P(improve) = alpha / (alpha + beta)."""
        self.ensure(arm)
        a, b = self.arms[arm]
        denom = a + b
        if denom <= 0:
            return 0.0
        return a / denom

    def hold_count(self, arm: str) -> int:
        return int(self.holds.get(arm, 0))

    def prune(self, *, k: int = DEFAULT_K, threshold: float = PRUNE_PROB_THRESHOLD) -> list[str]:
        """Arms to prune: >= K holds AND posterior P(improve) < threshold."""
        return [
            arm
            for arm in self.arms
            if self.holds.get(arm, 0) >= k and self.p_improve(arm) < threshold
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            arm: {
                "alpha": round(self.arms[arm][0], 4),
                "beta": round(self.arms[arm][1], 4),
                "holds": self.holds.get(arm, 0),
                "p_improve": round(self.p_improve(arm), 4),
            }
            for arm in self.arms
        }


def _bandit_from_optimizations(conn: sqlite3.Connection) -> Bandit:
    """Reconstruct the bandit from each applied rule's evidence_json."""
    rows = conn.execute(
        "SELECT block_key, evidence_json FROM optimizations WHERE status IN ('applied','pruned')"
    ).fetchall()
    bandit = Bandit()
    for r in rows:
        arm = str(r["block_key"])
        ev = _safe_json(r["evidence_json"])
        st = ev.get("bandit") or {}
        try:
            bandit.arms[arm] = [
                float(st.get("alpha", _ALPHA_PRIOR)),
                float(st.get("beta", _BETA_PRIOR)),
            ]
        except (TypeError, ValueError):
            bandit.arms[arm] = [_ALPHA_PRIOR, _BETA_PRIOR]
        bandit.holds[arm] = int(st.get("holds", 0))
    return bandit


def _persist_bandit(conn: sqlite3.Connection, bandit: Bandit) -> None:
    for arm, state in bandit.as_dict().items():
        row = conn.execute(
            "SELECT evidence_json FROM optimizations WHERE block_key = ?", (arm,)
        ).fetchone()
        if row is None:
            continue
        ev = _safe_json(row["evidence_json"])
        ev["bandit"] = state
        conn.execute(
            "UPDATE optimizations SET evidence_json = ? WHERE block_key = ?",
            (json.dumps(ev), arm),
        )


# ---------------------------------------------------------------------------
# The measured loop: measure -> bandit update -> prune -> auto-revert
# ---------------------------------------------------------------------------


def run_measurement(
    root: Path,
    *,
    m: int = DEFAULT_M,
    k: int = DEFAULT_K,
    threshold: float = PRUNE_PROB_THRESHOLD,
) -> dict[str, Any]:
    """Measure every applied rule on its holdout, update the bandit, prune regressions.

    Returns a summary the CLI/API can surface. Auto-reverts the managed block
    of any rule that regresses after the window.
    """
    db = root / ".cairn" / "ledger.db"
    if not db.is_file():
        return {"measured": 0, "pruned": [], "notes": ["no ledger"]}
    ledger = Ledger(db)
    measured: list[MeasuredRule] = []
    pruned_ids: list[str] = []
    try:
        conn = ledger.connection
        rows = conn.execute("SELECT * FROM optimizations WHERE status = 'applied'").fetchall()
        bandit = _bandit_from_optimizations(conn)
        for r in rows:
            res = measure_rule(conn, r, m=m)
            measured.append(res)
            if res.verdict == "insufficient":
                continue
            bandit.ensure(res.block_key)
            bandit.update(res.block_key, res.reward)
            _write_measurement(conn, r["opt_id"], res)
        _persist_bandit(conn, bandit)
        # Hard prune after K holds with P(improve) < threshold.
        for arm in bandit.prune(k=k, threshold=threshold):
            _set_status(conn, [arm], "pruned")
            _revert_block(root, arm)
            pruned_ids.append(arm)
        # Auto-revert any rule that regressed after its measurement window.
        for res in measured:
            if (
                res.verdict == "regressed"
                and bandit.hold_count(res.block_key) >= 1
                and _revert_block(root, res.block_key)
            ):
                _set_status(conn, [res.block_key], "pruned")
                if res.block_key not in pruned_ids:
                    pruned_ids.append(res.block_key)
        conn.commit()
    finally:
        ledger.close()
    return {
        "measured": len(measured),
        "verdicts": [
            {
                "block_key": m_.block_key,
                "verdict": m_.verdict,
                "baseline": m_.baseline_metric,
                "outcome": m_.outcome_metric,
                "fp_baseline": m_.fingerprint_distance_baseline,
                "fp_outcome": m_.fingerprint_distance_outcome,
                "reward": m_.reward,
                "outcome_sessions": m_.outcome_sessions,
                "holdout_size": len(m_.holdout),
                "pool_size": len(m_.proposal_pool),
                "p_improve": round(_bandit_p_improve(root, m_.block_key), 4),
            }
            for m_ in measured
        ],
        "pruned": pruned_ids,
        "bandit": _bandit_summary(root),
    }


def _write_measurement(conn: sqlite3.Connection, opt_id: str, res: MeasuredRule) -> None:
    causal = getattr(res, "_causal", None)
    effect_estimate = getattr(causal, "effect_estimate", None) if causal else None
    effect_ci_low = getattr(causal, "effect_ci_low", None) if causal else None
    effect_ci_high = getattr(causal, "effect_ci_high", None) if causal else None
    test_method = getattr(causal, "test_method", None) if causal else None
    confound_flag = 1 if causal and getattr(causal, "confound_flag", False) else 0
    conn.execute(
        """
        UPDATE optimizations
        SET outcome_metric = ?, outcome_sessions = ?,
            fingerprint_distance_outcome = ?, measured_at = ?,
            effect_estimate = ?, effect_ci_low = ?, effect_ci_high = ?,
            test_method = ?, confound_flag = ?
        WHERE opt_id = ?
        """,
        (
            res.outcome_metric,
            res.outcome_sessions,
            res.fingerprint_distance_outcome,
            _now_iso(),
            effect_estimate,
            effect_ci_low,
            effect_ci_high,
            test_method,
            confound_flag,
            opt_id,
        ),
    )


def _bandit_p_improve(root: Path, arm: str) -> float:
    db = root / ".cairn" / "ledger.db"
    if not db.is_file():
        return 0.0
    ledger = Ledger(db)
    try:
        bandit = _bandit_from_optimizations(ledger.connection)
        bandit.ensure(arm)
        return bandit.p_improve(arm)
    finally:
        ledger.close()


def _bandit_summary(root: Path) -> dict[str, Any]:
    db = root / ".cairn" / "ledger.db"
    if not db.is_file():
        return {}
    ledger = Ledger(db)
    try:
        return _bandit_from_optimizations(ledger.connection).as_dict()
    finally:
        ledger.close()


def _set_status(conn: sqlite3.Connection, entry_ids: list[str], status: str) -> None:
    if not entry_ids:
        return
    for eid in entry_ids:
        conn.execute(
            "UPDATE optimizations SET status = ? WHERE block_key = ?",
            (status, eid),
        )
    conn.commit()


def _revert_block(root: Path, entry_id: str) -> bool:
    """Remove a single entry from the AGENTS.md managed block; True if changed."""
    from cairn.optimize.apply import _agents_text, _existing_entries, replace_block

    current = _agents_text(root)
    entries = _existing_entries(current)
    kept = [e for e in entries if e.entry_id != entry_id]
    if len(kept) == len(entries):
        return False
    (root / "AGENTS.md").write_text(replace_block(current, kept), encoding="utf-8")
    return True


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
