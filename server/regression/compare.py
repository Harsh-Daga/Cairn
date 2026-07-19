"""Compare expected outcome vs recorded regression runs (no command execution)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from server.regression.schema import ExpectedOutcome, RegressionArtifact, RegressionRun
from server.regression.store import load_regression

CompareVerdict = Literal["match", "mismatch", "insufficient"]

_COMPARE_FIELDS = (
    "outcome_label",
    "tests_run",
    "tests_passed",
    "tests_failed",
    "build_status",
    "quality_score",
    "failure_signature",
)


def _field_diff(expected: ExpectedOutcome, observed: ExpectedOutcome) -> list[dict[str, Any]]:
    diffs: list[dict[str, Any]] = []
    for name in _COMPARE_FIELDS:
        left = getattr(expected, name)
        right = getattr(observed, name)
        if left is None and right is None:
            continue
        if left is None or right is None:
            diffs.append(
                {
                    "field": name,
                    "expected": left,
                    "observed": right,
                    "status": "insufficient",
                }
            )
            continue
        # Quality score: allow tiny float noise
        if name == "quality_score":
            if abs(float(left) - float(right)) > 1e-6:
                diffs.append(
                    {
                        "field": name,
                        "expected": left,
                        "observed": right,
                        "status": "mismatch",
                    }
                )
            continue
        if left != right:
            diffs.append(
                {
                    "field": name,
                    "expected": left,
                    "observed": right,
                    "status": "mismatch",
                }
            )
    return diffs


def _verdict(diffs: list[dict[str, Any]]) -> CompareVerdict:
    if any(item["status"] == "mismatch" for item in diffs):
        return "mismatch"
    if any(item["status"] == "insufficient" for item in diffs):
        return "insufficient"
    return "match"


def _select_run(
    artifact: RegressionArtifact,
    *,
    run_id: str | None,
) -> RegressionRun | dict[str, Any]:
    if not artifact.runs:
        return {"ok": False, "error": "no_runs", "message": "Record a run before comparing."}
    if run_id is None:
        return artifact.runs[-1]
    for run in artifact.runs:
        if run.run_id == run_id:
            return run
    return {"ok": False, "error": "run_not_found", "run_id": run_id}


def compare_regression(
    workspace_root: Path,
    *,
    regression_id: str,
    run_id: str | None = None,
    against: str = "expected",
) -> dict[str, Any]:
    """Diff expected outcome (or another run) against a recorded run. Never executes."""
    artifact = load_regression(workspace_root, regression_id)
    if artifact is None:
        return {"ok": False, "error": "regression_not_found", "regression_id": regression_id}

    selected = _select_run(artifact, run_id=run_id)
    if isinstance(selected, dict):
        return selected

    baseline_label = "expected"
    if against == "expected":
        baseline = artifact.expected_outcome
    else:
        other = _select_run(artifact, run_id=against)
        if isinstance(other, dict):
            return {**other, "error": other.get("error", "against_run_not_found")}
        baseline = other.observed
        baseline_label = other.run_id

    diffs = _field_diff(baseline, selected.observed)
    verdict = _verdict(diffs)
    return {
        "ok": True,
        "regression_id": regression_id,
        "run_id": selected.run_id,
        "against": baseline_label,
        "verdict": verdict,
        "diffs": diffs,
        "executed_commands": False,
        "limitation": (
            "Descriptive outcome rollup diff only. Cairn does not re-run agents or "
            "execute verification command hints."
        ),
    }
