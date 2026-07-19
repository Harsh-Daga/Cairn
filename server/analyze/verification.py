"""Deterministic verification receipts from recorded outcomes and spans.

Rules (receipt v1):
- absence of evidence is unverified, not false;
- only direct contradiction is contradicted (no claim ledger yet → no contradicted claims);
- optional LLM extraction cannot upgrade status;
- calculations are idempotent for the same recorded inputs.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Literal

from server.analyze.policy import evaluate_session_policy
from server.configuration import PolicyConfig, load_config
from server.models.outcome import Outcome
from server.models.span import Span
from server.models.trace import Trace
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.store.repos.workspaces import WorkspaceRepo

RECEIPT_SCHEMA_VERSION = "cairn.receipt.v1"
BUILDER_VERSION = "verification-receipt-v1"

VerificationStatus = Literal["verified", "failed", "debt", "unverified", "unknown"]
ClaimStatus = Literal["supported", "unsupported", "contradicted", "unverified"]

_VERIFY_NAME_RE = re.compile(
    r"\b(test|check|lint|build|verify|pytest|vitest|typecheck|mypy|ruff)\b",
    re.I,
)

# Transparent debt weights (documented; sum of active components is normalized to score).
DEBT_WEIGHTS: dict[str, float] = {
    "missing_tests": 0.30,
    "missing_build": 0.20,
    "missing_intent": 0.15,
    "success_without_checks": 0.25,
    "ordering_unproven": 0.10,
}


def verification_status_from_fields(
    *,
    tests_failed: int | None,
    build_status: str | None,
    tests_run: int | None,
    outcome_label: str | None,
    has_outcome: bool,
) -> VerificationStatus:
    """Map recorded outcome fields to a coarse verification status."""
    if not has_outcome:
        return "unknown"
    if int(tests_failed or 0) > 0 or str(build_status or "").lower() in {
        "fail",
        "failed",
        "error",
    }:
        return "failed"
    if int(tests_run or 0) > 0 or str(build_status or "").lower() in {
        "pass",
        "passed",
        "success",
    }:
        return "verified"
    if str(outcome_label or "").lower() in {"pass", "passed", "success"}:
        return "debt"
    return "unverified"


def verification_status_from_outcome(outcome: Outcome | None) -> VerificationStatus:
    """Map an Outcome model to a coarse verification status."""
    if outcome is None:
        return "unknown"
    return verification_status_from_fields(
        tests_failed=outcome.tests_failed,
        build_status=outcome.build_status,
        tests_run=outcome.tests_run,
        outcome_label=outcome.outcome_label,
        has_outcome=True,
    )


def build_receipt_dict(
    *,
    trace: Trace,
    spans: list[Span],
    outcome: Outcome | None,
    policy: PolicyConfig | None = None,
) -> dict[str, Any]:
    """Build a versioned receipt dictionary (idempotent for identical inputs)."""
    status = verification_status_from_outcome(outcome)
    intent_span = next(
        (span for span in sorted(spans, key=lambda item: item.seq) if span.kind == "user_msg"),
        None,
    )
    intent_text = (intent_span.text_inline or "").strip() if intent_span is not None else ""
    intent_present = bool(intent_text)

    debt_components = _debt_components(
        outcome=outcome,
        status=status,
        intent_present=intent_present,
    )
    active_weight = sum(float(item["weight"]) for item in debt_components if item["active"])
    debt_score = round(min(1.0, active_weight), 4)

    timeline = _timeline(spans, outcome)
    evidence_refs = _evidence_refs(spans, outcome, intent_span)
    requirements = _requirements(intent_present=intent_present, intent_span=intent_span)

    payload = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "trace_id": trace.trace_id,
        "status": status,
        "intent": {
            "present": intent_present,
            "span_id": intent_span.span_id if intent_span is not None else None,
            "summary": intent_text[:500] if intent_present else None,
            "limitation": (
                None if intent_present else "Original user goal was not retained in recorded spans."
            ),
        },
        "requirements": requirements,
        "claims": [],
        "claims_limitation": (
            "Observable agent completion claims and claim-to-evidence links are not "
            "extracted in receipt v1. Absence here is not a claim status of unsupported "
            "or contradicted."
        ),
        "evidence": evidence_refs,
        "timeline": timeline,
        "debt": {
            "score": debt_score,
            "components": debt_components,
            "explanation": (
                "Debt score is the sum of active component weights (capped at 1.0). "
                "Weights are descriptive of missing recorded evidence, not causal blame."
            ),
        },
        "outcome": {
            "label": outcome.outcome_label if outcome is not None else None,
            "tests_run": outcome.tests_run if outcome is not None else None,
            "tests_passed": outcome.tests_passed if outcome is not None else None,
            "tests_failed": outcome.tests_failed if outcome is not None else None,
            "build_status": outcome.build_status if outcome is not None else None,
            "human_label": outcome.human_label if outcome is not None else None,
            "quality_score": outcome.quality_score if outcome is not None else None,
        },
        "risk_policy": evaluate_session_policy(
            spans=spans,
            outcome=outcome,
            policy=policy or PolicyConfig(),
        ),
        "limitations": [
            "Receipt v1 uses recorded outcomes and verification-shaped spans only.",
            "Absence of evidence is unverified, not false.",
            "Cairn cannot prove validation occurred after the final relevant edit.",
            "Optional model extraction cannot override these deterministic fields.",
            "Policy findings are advisory observations and never claim Cairn blocked an action.",
        ],
    }
    payload["content_hash"] = _content_hash(payload)
    return payload


def build_receipt_for_trace(conn: sqlite3.Connection, trace_id: str) -> dict[str, Any] | None:
    """Load ledger rows and build a receipt, or None if the trace is missing."""
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    policy = None
    workspace = WorkspaceRepo.get(conn, trace.workspace_id)
    if workspace is not None and workspace.root_path:
        policy = load_config(Path(workspace.root_path)).policy
    spans = SpanRepo.list_by_trace(conn, trace_id)
    outcome = OutcomeRepo.get(conn, trace_id)
    return build_receipt_dict(trace=trace, spans=spans, outcome=outcome, policy=policy)


def render_receipt_markdown(receipt: dict[str, Any]) -> str:
    """Human-readable Markdown for CLI / copy."""
    lines = [
        f"# Cairn verification receipt · `{receipt['trace_id']}`",
        "",
        f"Schema: `{receipt['schema_version']}` · status: **{receipt['status']}**",
        "",
        "## Intent",
    ]
    intent = receipt["intent"]
    if intent.get("present"):
        lines.append(str(intent.get("summary") or ""))
    else:
        lines.append(str(intent.get("limitation") or "Intent unavailable."))
    lines.extend(["", "## Requirements"])
    for req in receipt.get("requirements") or []:
        lines.append(f"- [{req['status']}] {req['text']}")
    lines.extend(
        [
            "",
            "## Claims",
            str(receipt.get("claims_limitation") or "No claims."),
            "",
            "## Debt",
            f"Score: {receipt['debt']['score']}",
            str(receipt["debt"]["explanation"]),
        ]
    )
    for component in receipt["debt"]["components"]:
        marker = "active" if component["active"] else "inactive"
        lines.append(
            f"- `{component['id']}` ({marker}, weight={component['weight']}): {component['reason']}"
        )
    lines.extend(["", "## Timeline"])
    for event in receipt.get("timeline") or []:
        lines.append(f"- {event['at']}: {event['summary']}")
    if not receipt.get("timeline"):
        lines.append("- No verification-shaped events recorded.")
    lines.extend(["", "## Limitations"])
    for note in receipt.get("limitations") or []:
        lines.append(f"- {note}")
    lines.append("")
    return "\n".join(lines)


def _debt_components(
    *,
    outcome: Outcome | None,
    status: VerificationStatus,
    intent_present: bool,
) -> list[dict[str, Any]]:
    missing_tests = outcome is None or outcome.tests_run is None
    missing_build = outcome is None or outcome.build_status is None
    success_without = status == "debt"
    components = [
        {
            "id": "missing_tests",
            "weight": DEBT_WEIGHTS["missing_tests"],
            "active": missing_tests,
            "reason": (
                "Test execution is not recorded on the outcome row."
                if missing_tests
                else "Test execution was recorded."
            ),
        },
        {
            "id": "missing_build",
            "weight": DEBT_WEIGHTS["missing_build"],
            "active": missing_build,
            "reason": (
                "Build status is not recorded on the outcome row."
                if missing_build
                else "Build status was recorded."
            ),
        },
        {
            "id": "missing_intent",
            "weight": DEBT_WEIGHTS["missing_intent"],
            "active": not intent_present,
            "reason": (
                "No user_msg span with retained text was found."
                if not intent_present
                else "A user_msg span supplies an intent summary."
            ),
        },
        {
            "id": "success_without_checks",
            "weight": DEBT_WEIGHTS["success_without_checks"],
            "active": success_without,
            "reason": (
                "Outcome is labeled success without recorded tests or build status."
                if success_without
                else "No success-without-checks debt."
            ),
        },
        {
            "id": "ordering_unproven",
            "weight": DEBT_WEIGHTS["ordering_unproven"],
            "active": True,
            "reason": (
                "Receipt v1 cannot prove verification occurred after the final relevant edit."
            ),
        },
    ]
    return components


def _timeline(spans: list[Span], outcome: Outcome | None) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for span in sorted(spans, key=lambda item: item.seq):
        if span.status == "error" or _VERIFY_NAME_RE.search(span.name or ""):
            status = "failed" if span.status == "error" else "recorded"
            events.append(
                {
                    "kind": "span",
                    "at": f"seq {span.seq}",
                    "span_id": span.span_id,
                    "summary": f"{span.name or span.kind} · {status}",
                }
            )
    if outcome is not None:
        if outcome.tests_run is not None:
            events.append(
                {
                    "kind": "outcome_tests",
                    "at": "outcome",
                    "span_id": None,
                    "summary": (
                        f"tests_run={outcome.tests_run} passed={outcome.tests_passed} "
                        f"failed={outcome.tests_failed}"
                    ),
                }
            )
        if outcome.build_status is not None:
            events.append(
                {
                    "kind": "outcome_build",
                    "at": "outcome",
                    "span_id": None,
                    "summary": f"build_status={outcome.build_status}",
                }
            )
        if outcome.human_label is not None:
            events.append(
                {
                    "kind": "human_label",
                    "at": outcome.human_labeled_at or "outcome",
                    "span_id": None,
                    "summary": f"human_label={outcome.human_label}",
                }
            )
    return events[-20:]


def _evidence_refs(
    spans: list[Span],
    outcome: Outcome | None,
    intent_span: Span | None,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    if intent_span is not None:
        refs.append(
            {
                "kind": "intent_span",
                "span_id": intent_span.span_id,
                "label": "Retained user message",
            }
        )
    for span in spans:
        if span.status == "error" or _VERIFY_NAME_RE.search(span.name or ""):
            refs.append(
                {
                    "kind": "verification_span",
                    "span_id": span.span_id,
                    "label": f"seq {span.seq}: {span.name or span.kind}",
                }
            )
    if outcome is not None:
        refs.append(
            {
                "kind": "outcome",
                "span_id": None,
                "label": "Outcome row (tests/build/label)",
            }
        )
    return refs[:40]


def _requirements(*, intent_present: bool, intent_span: Span | None) -> list[dict[str, Any]]:
    if not intent_present:
        return [
            {
                "id": "req-intent",
                "text": "Capture or retain the original user goal for review.",
                "status": "unverified",
                "span_id": None,
            }
        ]
    return [
        {
            "id": "req-intent-review",
            "text": "Review the retained intent; atomic acceptance criteria were not extracted.",
            "status": "unverified",
            "span_id": intent_span.span_id if intent_span is not None else None,
        },
        {
            "id": "req-human-confirm",
            "text": "Confirm success criteria with a human unless explicitly recorded.",
            "status": "unverified",
            "span_id": None,
        },
    ]


def _content_hash(payload: dict[str, Any]) -> str:
    body = {key: value for key, value in payload.items() if key != "content_hash"}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
