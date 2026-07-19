"""Read-only MCP evidence tools: verification, policy preview, regression, next check."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from server.analyze.corrections import build_corrections_for_trace
from server.analyze.handoff import recommended_next_checks
from server.analyze.policy import evaluate_session_policy
from server.analyze.verification import build_receipt_for_trace
from server.configuration import load_config
from server.export.scrub import scrub_text
from server.mcp.context_budget import resolve_trace
from server.models.outcome import Outcome
from server.models.span import Span
from server.regression.store import list_regressions, load_regression
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.spans import SpanRepo

ApprovalClass = str  # read_only | local_test | mutating | destructive


def verification_status(
    conn: sqlite3.Connection,
    workspace_id: str | None,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Compact receipt summary and remaining checks. No mutation / provider call."""
    requested = str(args.get("trace_id") or args.get("session_id") or "").strip() or None
    resolution = resolve_trace(conn, workspace_id, requested)
    if resolution.get("error"):
        return resolution
    trace_id = str(resolution["trace_id"])
    receipt = build_receipt_for_trace(conn, trace_id)
    if receipt is None:
        return {"error": "trace_not_found", "trace_id": trace_id}
    active_debt = [
        {
            "id": component["id"],
            "reason": component.get("reason"),
            "weight": component.get("weight"),
        }
        for component in receipt.get("debt", {}).get("components", [])
        if component.get("active")
    ]
    remaining = [
        {"id": req["id"], "text": req["text"], "status": req["status"]}
        for req in receipt.get("requirements") or []
        if req.get("status") != "met"
    ]
    return {
        "schema": "cairn.mcp.verification_status.v1",
        "trace_id": trace_id,
        "status": receipt.get("status"),
        "debt_score": receipt.get("debt", {}).get("score"),
        "active_debt": active_debt,
        "remaining_checks": remaining,
        "review_risk": receipt.get("risk_policy", {}).get("review_risk"),
        "data_as_of": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "content_hash": receipt.get("content_hash"),
        "limitations": [
            "Read-only summary; claims ledger is empty until claim extraction lands.",
            "No provider or network call.",
        ],
        "consultation": "recorded",
    }


def policy_check(
    conn: sqlite3.Connection,
    workspace_root: Path,
    workspace_id: str | None,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Advisory evaluation of a proposed path/command/change. Never executes."""
    del conn, workspace_id
    path = str(args.get("path") or args.get("path_rel") or "").strip() or None
    command = str(args.get("command") or "").strip() or None
    if not path and not command:
        return {
            "error": "path_or_command_required",
            "limitation": "Pass path and/or command to evaluate against [policy].",
        }
    policy = load_config(workspace_root).policy
    # Evaluate against caller-provided literals; scrub only in the response.
    spans: list[Span] = []
    if command:
        spans.append(
            Span(
                span_id="proposed-cmd",
                trace_id="proposed",
                seq=1,
                kind="tool_call",
                name=command[:200],
                status="ok",
                path_rel=path[:200] if path else None,
            )
        )
    elif path:
        spans.append(
            Span(
                span_id="proposed-path",
                trace_id="proposed",
                seq=1,
                kind="tool_call",
                name="propose",
                status="ok",
                path_rel=path[:200],
            )
        )
    files = [path] if path else None
    outcome = Outcome(trace_id="proposed", files_changed=files) if files else None
    result = evaluate_session_policy(spans=spans, outcome=outcome, policy=policy)
    return {
        "schema": "cairn.mcp.policy_check.v1",
        "proposed": {
            "path": scrub_text(path, workspace_root) if path else None,
            "command": scrub_text(command, workspace_root) if command else None,
        },
        "review_risk": result.get("review_risk"),
        "findings": result.get("findings") or [],
        "evaluated": result.get("evaluated"),
        "data_as_of": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "limitation": result.get("limitation"),
        "enforcement_note": result.get("enforcement_note"),
        "consultation": "recorded",
        "executed": False,
    }


def regression_context(
    workspace_root: Path,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Load a selected local regression's acceptance criteria. No execution."""
    regression_id = str(args.get("regression_id") or "").strip() or None
    if not regression_id:
        items = list_regressions(workspace_root)
        if len(items) == 0:
            return {
                "error": "no_regressions",
                "limitation": "No local regressions under .cairn/regressions.",
            }
        if len(items) > 1:
            return {
                "error": "ambiguous_regression",
                "candidates": [
                    {
                        "regression_id": item.regression_id,
                        "title": item.title,
                        "created_at": item.created_at,
                    }
                    for item in items[:10]
                ],
                "limitation": "Pass regression_id when more than one artifact exists.",
            }
        regression_id = items[0].regression_id
    artifact = load_regression(workspace_root, regression_id)
    if artifact is None:
        return {"error": "regression_not_found", "regression_id": regression_id}
    return {
        "schema": "cairn.mcp.regression_context.v1",
        "regression_id": artifact.regression_id,
        "scrubbed_task": artifact.scrubbed_task,
        "repo_start_ref": artifact.repo_start_ref.model_dump(mode="json"),
        "verification_commands": [
            cmd.model_dump(mode="json") for cmd in artifact.verification_commands
        ],
        "setup_commands": [cmd.model_dump(mode="json") for cmd in artifact.setup_commands],
        "expected_outcome": artifact.expected_outcome.model_dump(mode="json"),
        "required_paths": artifact.required_paths,
        "prohibited_changes": artifact.prohibited_changes,
        "limitations": artifact.limitations,
        "privacy_inventory": artifact.privacy_inventory.model_dump(mode="json"),
        "executed": False,
        "consultation": "recorded",
        "data_as_of": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }


def next_evidence(
    conn: sqlite3.Connection,
    workspace_root: Path,
    workspace_id: str | None,
    args: dict[str, Any],
) -> dict[str, Any]:
    """Smallest repository-grounded next check preview. Never executes."""
    requested = str(args.get("trace_id") or args.get("session_id") or "").strip() or None
    resolution = resolve_trace(conn, workspace_id, requested)
    if resolution.get("error"):
        return resolution
    trace_id = str(resolution["trace_id"])
    receipt = build_receipt_for_trace(conn, trace_id)
    if receipt is None:
        return {"error": "trace_not_found", "trace_id": trace_id}
    outcome = OutcomeRepo.get(conn, trace_id)
    spans = SpanRepo.list_by_trace(conn, trace_id)
    corrections = build_corrections_for_trace(conn, trace_id)
    checks = recommended_next_checks(receipt, outcome, corrections)
    primary = (
        checks[0]
        if checks
        else {
            "kind": "recommendation",
            "text": "No further automated check could be grounded in the ledger.",
        }
    )
    approval, side_effects, est_cost = _classify_check(str(primary.get("text") or ""))
    config = load_config(workspace_root)
    test_cmd = config.tests.get("default") if isinstance(config.tests, dict) else None
    return {
        "schema": "cairn.mcp.next_evidence.v1",
        "trace_id": trace_id,
        "next_check": {
            "text": primary.get("text"),
            "kind": primary.get("kind"),
            "approval_class": approval,
            "side_effects": side_effects,
            "estimated_cost": est_cost,
            "suggested_command": test_cmd,
            "executed": False,
        },
        "alternates": [
            {"text": item.get("text"), "kind": item.get("kind")} for item in checks[1:3]
        ],
        "receipt_status": receipt.get("status"),
        "debt_score": receipt.get("debt", {}).get("score"),
        "span_count": len(spans),
        "data_as_of": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "limitations": [
            "Preview only — Cairn does not run the suggested check.",
            "Cost/side-effect estimates are conservative heuristics, not measurements.",
            "Prefer repository-grounded commands from config.tests when present.",
        ],
        "consultation": "recorded",
    }


def _classify_check(text: str) -> tuple[ApprovalClass, list[str], dict[str, Any]]:
    lowered = text.lower()
    if any(token in lowered for token in ("drop ", "rm -rf", "delete ", "force push")):
        return (
            "destructive",
            ["may destroy data", "requires explicit human approval"],
            {"kind": "unavailable", "note": "Destructive checks are never auto-run."},
        )
    if any(
        token in lowered for token in ("test", "pytest", "vitest", "typecheck", "lint", "build")
    ):
        return (
            "local_test",
            ["may spend CPU/time", "writes only under normal test outputs"],
            {
                "kind": "estimated",
                "tokens": None,
                "usd": None,
                "note": "Local test/build cost unknown.",
            },
        )
    if any(token in lowered for token in ("read", "inspect", "spot-check", "review")):
        return (
            "read_only",
            ["no writes expected"],
            {
                "kind": "estimated",
                "tokens": None,
                "usd": None,
                "note": "Human/read inspection.",
            },
        )
    return (
        "mutating",
        ["may modify the workspace if executed by an agent"],
        {"kind": "unavailable", "note": "Approval required before any mutation."},
    )
