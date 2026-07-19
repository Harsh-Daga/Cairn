"""Record a later observed run from an ingested trace (no command execution)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.export.scrub import scrub_text
from server.regression.schema import ExpectedOutcome, RegressionArtifact, RegressionRun
from server.regression.store import load_regression, save_regression
from server.store.repos.diagnostics import DiagnosticRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.traces import TraceRepo
from server.util.ids import new_ulid


def _observed_from_trace(
    conn: sqlite3.Connection,
    *,
    workspace_root: Path,
    workspace_id: str,
    trace_id: str,
) -> tuple[ExpectedOutcome, str | None, str | None] | dict[str, Any]:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None or trace.workspace_id != workspace_id:
        return {"ok": False, "error": "trace_not_found", "trace_id": trace_id}
    outcome = OutcomeRepo.get(conn, trace_id)
    diagnostic = DiagnosticRepo.get(conn, trace_id)
    signature = diagnostic.failure_signature if diagnostic is not None else None
    if signature:
        signature = scrub_text(str(signature), workspace_root)
    observed = ExpectedOutcome(
        outcome_label=outcome.outcome_label if outcome else None,
        tests_run=outcome.tests_run if outcome else None,
        tests_passed=outcome.tests_passed if outcome else None,
        tests_failed=outcome.tests_failed if outcome else None,
        build_status=outcome.build_status if outcome else None,
        quality_score=outcome.quality_score if outcome else None,
        failure_signature=signature,
    )
    return observed, trace.source, trace.git_commit


def record_run_from_trace(
    conn: sqlite3.Connection,
    *,
    workspace_root: Path,
    workspace_id: str,
    regression_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """Append one observed run from a ledger trace. Never executes commands."""
    artifact = load_regression(workspace_root, regression_id)
    if artifact is None:
        return {"ok": False, "error": "regression_not_found", "regression_id": regression_id}

    pulled = _observed_from_trace(
        conn,
        workspace_root=workspace_root,
        workspace_id=workspace_id,
        trace_id=trace_id,
    )
    if isinstance(pulled, dict):
        return pulled
    observed, agent_source, commit = pulled

    recorded_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    run = RegressionRun(
        run_id=new_ulid(),
        recorded_at=recorded_at,
        source_trace_id=trace_id,
        agent_source=agent_source,
        observed=observed,
        repo_ref=commit,
        executed_commands=False,
        limitations=[
            "Recorded from an already-ingested session; Cairn did not re-run the agent.",
            "Setup and verification command hints are never executed.",
        ],
    )
    runs = [*artifact.runs, run]
    updated = artifact.model_copy(update={"runs": runs})
    # Keep definition content_hash stable across run appends.
    save_regression(
        workspace_root,
        updated,
        title=updated.scrubbed_task,
    )
    return {
        "ok": True,
        "regression_id": regression_id,
        "run_id": run.run_id,
        "source_trace_id": trace_id,
        "runs": len(runs),
        "content_hash": artifact.content_hash,
        "executed_commands": False,
    }


def load_artifact_or_error(
    workspace_root: Path, regression_id: str
) -> RegressionArtifact | dict[str, Any]:
    artifact = load_regression(workspace_root, regression_id)
    if artifact is None:
        return {"ok": False, "error": "regression_not_found", "regression_id": regression_id}
    return artifact
