"""Pillar 3 — outcomes + Agent Quality Score (Part 11 + §2.7B)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

from cairn.outcomes.git import GitSignals, capture_git_signals
from cairn.outcomes.score import (
    ProcessScore,
    agent_quality_score,
    cost_per_success,
    is_lucky_pass,
    process_quality_score,
)
from cairn.outcomes.tests import TestResult, run_tests

__all__ = [
    "GitSignals",
    "ProcessScore",
    "TestResult",
    "agent_quality_score",
    "backfill_outcome",
    "capture_git_signals",
    "cost_per_success",
    "is_lucky_pass",
    "outcomes_payload",
    "process_quality_score",
    "run_tests",
]

CONTEXT_ROT_PENALTY = 1.0  # multiplier on peak_context_pct; configurable later


def backfill_outcome(
    writer: Any, run_id: str, *, events: list[dict[str, Any]] | None = None
) -> None:
    """Capture + store the outcome row for a run (idempotent)."""
    conn = writer.connection
    if events is None:
        events = writer.load_events(run_id)
    run = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run is None:
        return

    git = capture_git_signals(run["cwd"], run["started_at"], run["ended_at"])
    tests = run_tests(run["cwd"], run["project"])

    # Fingerprint drift distance for fingerprint_stability + Lucky-Pass context.
    fp_distance, fp_threshold = _drift_distance(conn, run)

    total_tokens = int(run["total_input_tokens"] or 0) + int(run["total_output_tokens"] or 0)
    tool_call_count = int(run["tool_call_count"] or 0)
    retry_rate = _retry_rate(events)
    error_rate = (int(run["tool_error_count"] or 0) / tool_call_count) if tool_call_count else 0.0

    quality = agent_quality_score(
        commit_landed=git.commit_landed,
        tests_passed=tests.tests_passed,
        tests_failed=tests.tests_failed,
        build_status=tests.build_status,
        waste_tokens=int(run["waste_tokens"] or 0),
        total_tokens=total_tokens,
        peak_context_pct=run["peak_context_pct"],
        context_rot_penalty=CONTEXT_ROT_PENALTY,
        retry_rate=retry_rate,
        error_rate=error_rate,
        mahalanobis_distance=fp_distance,
        drift_threshold=fp_threshold,
    )

    process = process_quality_score(events)
    lucky = is_lucky_pass(process, git.commit_landed)

    # Per-run cost_per_success contribution: the run's cost if it is a non-Lucky
    # success, else NULL. The cohort aggregate is computed in outcomes_payload.
    is_success = bool(
        git.commit_landed
        and not lucky
        and (tests.tests_passed is None or (tests.tests_passed or 0) > (tests.tests_failed or 0))
    )
    cps = float(run["total_cost"] or 0.0) if is_success else None

    files_payload = {
        "files": git.files_changed,
        "lucky_pass": lucky,
        "tier": process.tier,
        "process_score": process.score,
        "intent_stages": process.intent_stages,
        "process_signals": process.signals,
        "uncommitted": git.uncommitted,
        "quality_components": quality.components,
    }

    writer.write_outcome(
        run_id,
        commit_sha=git.commit_sha,
        commit_landed=git.commit_landed,
        files_changed=files_payload,  # packed dict; writer json-encodes
        tests_run=tests.tests_run,
        tests_passed=tests.tests_passed,
        tests_failed=tests.tests_failed,
        build_status=tests.build_status,
        quality_score=quality.score,
        cost_per_success=cps,
        captured_at=datetime.now(UTC).isoformat(),
    )

    notes = git.data_notes + tests.data_notes
    if fp_distance is None:
        notes.append("no fingerprint baseline; fingerprint_stability=0")
    _stash_notes(conn, run_id, notes)


def _stash_notes(conn: Any, run_id: str, notes: list[str]) -> None:
    """Persist outcome data-notes alongside the row (packed into files_changed_json)."""
    if not notes:
        return
    row = conn.execute(
        "SELECT files_changed_json FROM outcomes WHERE run_id = ?", (run_id,)
    ).fetchone()
    if row is None or not row["files_changed_json"]:
        return
    try:
        payload = json.loads(row["files_changed_json"])
    except json.JSONDecodeError:
        return
    if isinstance(payload, dict):
        payload["data_notes"] = notes
        conn.execute(
            "UPDATE outcomes SET files_changed_json = ? WHERE run_id = ?",
            (json.dumps(payload), run_id),
        )


def _retry_rate(events: list[dict[str, Any]]) -> float:
    from cairn.metrics.waste import compute_waste

    waste = compute_waste(events, has_cost=False, peak_context_pct=None)
    retry = sum(1 for _, cat, _ in waste.tags if cat in ("retry_loop", "blind_retry"))
    tool_calls = sum(1 for e in events if e.get("type") == "tool_call")
    return retry / tool_calls if tool_calls else 0.0


def _drift_distance(conn: Any, run: Any) -> tuple[float | None, float | None]:
    """Mahalanobis distance + χ² threshold for the run vs its prior baseline."""
    fp = conn.execute(
        "SELECT vector_json, project, model, week FROM fingerprints WHERE run_id = ?",
        (run["run_id"],),
    ).fetchone()
    if fp is None or not fp["vector_json"]:
        return None, None
    try:
        vec = json.loads(fp["vector_json"])
    except json.JSONDecodeError:
        return None, None
    from cairn.metrics.fingerprint import _baseline_vectors_for, detect_drift

    baseline = _baseline_vectors_for(
        conn, str(fp["project"] or ""), str(fp["model"] or ""), before_week=fp["week"]
    )
    if len(baseline) < 4:
        return None, None
    res = detect_drift(vec, baseline)
    if res.d_eff == 0:
        return None, None
    return res.distance, res.threshold


# ---------------------------------------------------------------------------
# API payload
# ---------------------------------------------------------------------------


def outcomes_payload(conn: Any, *, days: int = 30) -> dict[str, Any]:
    """``GET /api/outcomes`` — quality + cost-per-success + funnel."""
    rows = conn.execute(
        """
        SELECT o.run_id, o.commit_sha, o.commit_landed, o.files_changed_json,
               o.tests_run, o.tests_passed, o.tests_failed, o.build_status,
               o.quality_score, o.cost_per_success, o.captured_at,
               r.total_cost, r.has_cost, r.project, r.source, r.started_at
        FROM outcomes o JOIN runs r ON o.run_id = r.run_id
        WHERE r.started_at >= date('now', ?)
        ORDER BY r.started_at DESC
        """,
        (f"-{days} days",),
    ).fetchall()

    if not rows:
        return {
            "quality": None,
            "cost_per_success": None,
            "funnel": None,
            "sessions": None,
            "data_notes": [
                "no outcomes in range",
                "configure test_command in ~/.cairn/config.toml to enable test tracking",
            ],
        }

    sessions: list[dict[str, Any]] = []
    cps_rows: list[dict[str, Any]] = []
    tests_configured = False
    for r in rows:
        payload = _parse_files(r["files_changed_json"])
        lucky = bool(payload.get("lucky_pass"))
        tier = payload.get("tier")
        commit_landed = bool(r["commit_landed"])
        if r["build_status"] not in (None, "unknown"):
            tests_configured = True
        sessions.append(
            {
                "run_id": r["run_id"],
                "project": r["project"],
                "commit_landed": commit_landed,
                "commit_sha": r["commit_sha"],
                "tier": tier,
                "lucky_pass": lucky,
                "quality_score": r["quality_score"],
                "tests": {
                    "run": r["tests_run"],
                    "passed": r["tests_passed"],
                    "failed": r["tests_failed"],
                    "build_status": r["build_status"],
                },
                "cost_per_success": r["cost_per_success"],
                "process_score": payload.get("process_score"),
                "intent_stages": payload.get("intent_stages"),
                "process_signals": payload.get("process_signals"),
                "data_notes": payload.get("data_notes", []),
            }
        )
        cps_rows.append(
            {
                "total_cost": float(r["total_cost"] or 0.0),
                "commit_landed": commit_landed,
                "lucky_pass": lucky,
            }
        )

    cps = cost_per_success(cps_rows)
    funnel = _funnel(rows, sessions)

    notes: list[str] = []
    if not tests_configured:
        notes.append(
            "test_command not configured: build_status is 'unknown' "
            "(default OFF; configure in ~/.cairn/config.toml)"
        )
    if not any(r["has_cost"] for r in rows):
        notes.append("has_cost=0 for all sessions: cost_per_success is null")

    scores = [s["quality_score"] for s in sessions if s["quality_score"] is not None]
    quality = {
        "mean": round(sum(scores) / len(scores), 2) if scores else None,
        "tier_counts": _tier_counts(sessions),
    }
    return {
        "quality": quality,
        "cost_per_success": cps,
        "funnel": funnel,
        "sessions": sessions,
        "data_notes": notes,
    }


def _funnel(rows: Any, sessions: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    commits = sum(1 for s in sessions if s["commit_landed"])
    passing = sum(1 for s in sessions if s["tests"]["build_status"] == "pass")
    return {
        "sessions": total,
        "commits_landed": commits,
        "passing_tests": passing,
    }


def _tier_counts(sessions: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {"Ideal": 0, "Solid": 0, "Lucky": 0, "unknown": 0}
    for s in sessions:
        t = s.get("tier") or "unknown"
        counts[t] = counts.get(t, 0) + 1
    return counts


def _parse_files(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, list):
        # Legacy/forward-compat: a bare list of files.
        return {"files": payload}
    if isinstance(payload, dict):
        return cast(dict[str, Any], payload)
    return {}
