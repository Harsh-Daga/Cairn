"""Diagnosis orchestration — Phase A."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cairn.config import get_diagnose_setting
from cairn.diagnose.cascade import detect_cascade
from cairn.diagnose.ideal import ideal_path_savings
from cairn.diagnose.localize import localize_failure
from cairn.diagnose.taxonomy import classify_failure
from cairn.outcomes.labels import derive_outcome_label


def compute_diagnostics(
    run: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    git_landed: bool = False,
    tests_passed: int | None = None,
    tests_failed: int | None = None,
    status: str = "completed",
) -> dict[str, Any]:
    """Full diagnostics payload for one run."""
    outcome_label, label_source = derive_outcome_label(
        git_landed=git_landed,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        status=status,
        events=events,
    )
    origin_id, signature, _one_liner = localize_failure(events)
    if outcome_label == "landed":
        origin_id, signature = None, None
    cascade_root, _blast_events, blast_tokens = detect_cascade(events)
    cascade_skipped = len(events) > int(get_diagnose_setting("cascade_max_events"))
    savings, _ideal = ideal_path_savings(events)
    primary, secondary = classify_failure(
        events,
        outcome_label=outcome_label,
        failure_signature=signature,
    )
    return {
        "outcome_label": outcome_label,
        "label_source": label_source,
        "failure_origin_event_id": origin_id,
        "failure_signature": signature,
        "primary_category": primary,
        "secondary_category": secondary,
        "cascade_root_event_id": cascade_root,
        "cascade_blast_tokens": blast_tokens or None,
        "ideal_path_savings_tokens": savings,
        "ideal_path": _ideal,
        "cascade_skipped": cascade_skipped,
        "computed_at": datetime.now(UTC).isoformat(),
    }


def backfill_diagnostics(
    writer: Any, run_id: str, *, events: list[dict[str, Any]] | None = None
) -> None:
    conn = writer.connection
    if events is None:
        events = writer.load_events(run_id)
    # Attach event_id from DB if missing (load_events includes it).
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        return
    run = dict(run_row)
    out_row = conn.execute(
        "SELECT commit_landed, tests_passed, tests_failed FROM outcomes WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    git_landed = bool(out_row["commit_landed"]) if out_row else False
    tests_passed = (
        int(out_row["tests_passed"]) if out_row and out_row["tests_passed"] is not None else None
    )
    tests_failed = (
        int(out_row["tests_failed"]) if out_row and out_row["tests_failed"] is not None else None
    )
    diag = compute_diagnostics(
        run,
        events,
        git_landed=git_landed,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        status=str(run.get("status") or "completed"),
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO diagnostics (
          run_id, outcome_label, label_source, failure_origin_event_id,
          failure_signature, primary_category, secondary_category,
          cascade_root_event_id, cascade_blast_tokens, ideal_path_savings_tokens,
          computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            diag["outcome_label"],
            diag["label_source"],
            diag["failure_origin_event_id"],
            diag["failure_signature"],
            diag["primary_category"],
            diag["secondary_category"],
            diag["cascade_root_event_id"],
            diag["cascade_blast_tokens"],
            diag["ideal_path_savings_tokens"],
            diag["computed_at"],
        ),
    )
    if out_row is not None:
        conn.execute(
            "UPDATE outcomes SET outcome_label = ?, label_source = ? WHERE run_id = ?",
            (diag["outcome_label"], diag["label_source"], run_id),
        )
    conn.commit()


def backfill_difficulty(
    writer: Any, run_id: str, *, events: list[dict[str, Any]] | None = None
) -> None:
    from cairn.metrics.difficulty import estimate_difficulty, features_json
    from cairn.metrics.normalized import backfill_expectations_for_run

    conn = writer.connection
    if events is None:
        events = writer.load_events(run_id)
    run_row = conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
    if run_row is None:
        return
    run = dict(run_row)
    score = estimate_difficulty(run, events)
    conn.execute(
        """
        UPDATE runs SET difficulty = ?, difficulty_bucket = ?, difficulty_features_json = ?
        WHERE run_id = ?
        """,
        (score.difficulty, score.bucket, features_json(score), run_id),
    )
    run["difficulty"] = score.difficulty
    run["difficulty_bucket"] = score.bucket
    backfill_expectations_for_run(conn, run)
    conn.commit()
