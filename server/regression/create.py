"""Create a scrubbed regression artifact from a recorded session."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server import __version__
from server.analyze.verification import build_receipt_for_trace
from server.export.scrub import scrub_text
from server.regression.schema import (
    REGRESSION_SCHEMA_VERSION,
    CommandHint,
    ExpectedOutcome,
    PrivacyInventory,
    Provenance,
    RegressionArtifact,
    RepoStartRef,
)
from server.regression.store import save_regression
from server.store.repos.diagnostics import DiagnosticRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.util.ids import new_ulid

_VERIFY_NAME_RE = re.compile(
    r"\b(test|check|lint|build|verify|pytest|vitest|typecheck|mypy|ruff)\b",
    re.I,
)


def create_regression_from_trace(
    conn: sqlite3.Connection,
    *,
    workspace_root: Path,
    workspace_id: str,
    trace_id: str,
) -> dict[str, Any]:
    """Build and persist a local regression artifact. Does not execute commands."""
    trace = TraceRepo.get(conn, trace_id)
    if trace is None or trace.workspace_id != workspace_id:
        return {"ok": False, "error": "trace_not_found", "trace_id": trace_id}

    spans = SpanRepo.list_by_trace(conn, trace_id)
    outcome = OutcomeRepo.get(conn, trace_id)
    diagnostic = DiagnosticRepo.get(conn, trace_id)
    receipt = build_receipt_for_trace(conn, trace_id)

    intent = None
    task_source: Any = "missing"
    if receipt and receipt["intent"].get("present"):
        intent = scrub_text(str(receipt["intent"].get("summary") or ""), workspace_root)
        task_source = "receipt_intent"
    else:
        for span in sorted(spans, key=lambda item: item.seq):
            if span.kind == "user_msg" and span.text_inline:
                intent = scrub_text(span.text_inline, workspace_root)
                task_source = "user_msg"
                break

    commit = None
    commit_source: Any = "missing"
    if outcome is not None and outcome.commit_sha:
        commit = outcome.commit_sha
        commit_source = "outcome"
    elif trace.git_commit:
        commit = trace.git_commit
        commit_source = "trace"

    verification_commands: list[CommandHint] = []
    seen: set[str] = set()
    for span in spans:
        name = (span.name or "").strip()
        if not name or not _VERIFY_NAME_RE.search(name):
            continue
        if name in seen:
            continue
        seen.add(name)
        verification_commands.append(
            CommandHint(
                command=scrub_text(name, workspace_root),
                source="inferred",
                span_id=span.span_id,
            )
        )

    required_paths: list[str] = []
    if outcome is not None and outcome.files_changed:
        for file_path in outcome.files_changed[:20]:
            required_paths.append(scrub_text(str(file_path), workspace_root))

    created_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    regression_id = new_ulid()
    artifact = RegressionArtifact(
        schema_version=REGRESSION_SCHEMA_VERSION,
        regression_id=regression_id,
        scrubbed_task=intent,
        task_source=task_source,
        repo_start_ref=RepoStartRef(
            commit=commit,
            commit_source=commit_source,
            fixture=None,
            limitation=(None if commit else "No commit SHA was recorded on the outcome or trace."),
        ),
        setup_commands=[],
        verification_commands=verification_commands,
        expected_outcome=ExpectedOutcome(
            outcome_label=outcome.outcome_label if outcome else None,
            tests_run=outcome.tests_run if outcome else None,
            tests_passed=outcome.tests_passed if outcome else None,
            tests_failed=outcome.tests_failed if outcome else None,
            build_status=outcome.build_status if outcome else None,
            quality_score=outcome.quality_score if outcome else None,
            failure_signature=(diagnostic.failure_signature if diagnostic is not None else None),
        ),
        prohibited_changes=[],
        required_paths=required_paths,
        resource_limit=None,
        provenance=Provenance(
            source_trace_id=trace_id,
            agent_source=trace.source,
            created_at=created_at,
            producer_version=__version__,
        ),
        privacy_inventory=PrivacyInventory(
            scrubbed=True,
            included=[
                "scrubbed task summary",
                "outcome rollups",
                "inferred verification command names",
                "repo commit reference when recorded",
            ],
            redacted=[
                "raw transcript text",
                "absolute paths and secrets",
                "repository contents / patches",
            ],
            notes=[
                "Attachments are empty by default; Cairn does not copy the working tree.",
            ],
        ),
        attachments=[],
        runs=[],
        limitations=[
            "Setup commands are not recorded and remain empty.",
            "Verification command names are inferred from spans and are not executed.",
            "Prohibited changes are empty until manually edited.",
            "No arbitrary command execution is performed when creating this artifact.",
            "Use `cairn regression run` to record a later observed session; compare never executes.",
        ],
    )
    body = artifact.model_dump(mode="json")
    body.pop("content_hash", None)
    body.pop("runs", None)  # definition identity excludes recorded runs
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    artifact = artifact.model_copy(update={"content_hash": digest})
    path = save_regression(workspace_root, artifact, title=intent)
    return {
        "ok": True,
        "schema": REGRESSION_SCHEMA_VERSION,
        "regression_id": regression_id,
        "path": str(path),
        "content_hash": digest,
        "source_trace_id": trace_id,
    }
