"""Validate local regression artifacts without executing commands."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from server.regression.schema import REGRESSION_SCHEMA_VERSION, RegressionArtifact


def validate_artifact(artifact: RegressionArtifact) -> dict[str, Any]:
    """Return a structured validation report. Never executes commands."""
    errors: list[str] = []
    warnings: list[str] = []

    if artifact.schema_version != REGRESSION_SCHEMA_VERSION:
        errors.append(
            f"unsupported schema_version {artifact.schema_version!r}; "
            f"expected {REGRESSION_SCHEMA_VERSION!r}"
        )
    if not artifact.regression_id:
        errors.append("regression_id is required")
    if not artifact.provenance.source_trace_id:
        errors.append("provenance.source_trace_id is required")
    if not artifact.content_hash:
        errors.append("content_hash is required")

    if artifact.scrubbed_task is None:
        warnings.append("scrubbed_task is missing; task intent was not recorded")
    if artifact.repo_start_ref.commit is None and artifact.repo_start_ref.fixture is None:
        warnings.append(
            "repo_start_ref has neither commit nor fixture; reproduction may be incomplete"
        )
    if artifact.setup_commands:
        warnings.append(
            "setup_commands are present but Cairn does not execute them; "
            "treat as documentation only"
        )
    if artifact.verification_commands:
        inferred = [c for c in artifact.verification_commands if c.source == "inferred"]
        if inferred:
            warnings.append(
                f"{len(inferred)} verification command(s) are inferred hints and are not executed"
            )
    else:
        warnings.append("no verification_commands recorded")
    if not artifact.privacy_inventory.scrubbed:
        errors.append("privacy_inventory.scrubbed must be true for portable artifacts")

    for index, run in enumerate(artifact.runs):
        if run.executed_commands:
            errors.append(
                f"runs[{index}].executed_commands must be false; "
                "Cairn never executes setup/verification commands"
            )
        if not run.run_id or not run.source_trace_id:
            errors.append(f"runs[{index}] requires run_id and source_trace_id")

    return {
        "ok": not errors,
        "schema": REGRESSION_SCHEMA_VERSION,
        "regression_id": artifact.regression_id,
        "errors": errors,
        "warnings": warnings,
        "executed_commands": False,
        "run_count": len(artifact.runs),
        "limitation": (
            "Validation checks schema and honesty constraints only; "
            "no setup or verification commands are run."
        ),
    }


def validate_payload(payload: dict[str, Any] | str | bytes) -> dict[str, Any]:
    try:
        if isinstance(payload, (str, bytes)):
            artifact = RegressionArtifact.model_validate_json(payload)
        else:
            artifact = RegressionArtifact.model_validate(payload)
    except ValidationError as exc:
        return {
            "ok": False,
            "schema": REGRESSION_SCHEMA_VERSION,
            "regression_id": None,
            "errors": [f"schema validation failed: {exc.error_count()} issue(s)"],
            "warnings": [],
            "executed_commands": False,
            "limitation": "Payload did not match cairn.regression.v1.",
            "details": exc.errors(),
        }
    return validate_artifact(artifact)
