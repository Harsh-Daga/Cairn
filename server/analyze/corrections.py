"""Conservative correction classifier and recovery linkage.

Rules:
- Prefer false negatives over false positives (high-precision phrases only).
- Absence of a match is not "no supervision tax".
- User relabels override class locally and never leave the machine by default.
- No employee ranking or cross-user aggregates.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from typing import Any, Literal

from server.models.span import Span
from server.models.trace import Trace
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.util.ids import new_ulid

CORRECTIONS_SCHEMA_VERSION = "cairn.corrections.v1"
BUILDER_VERSION = "corrections-v1"

CorrectionClass = Literal[
    "project_reading_failure",
    "intent_misunderstanding",
    "instruction_rule_violation",
    "scope_boundary_violation",
    "implementation_failure",
    "execution_verification_failure",
    "misleading_progress_reporting",
    "unclassified",
]

RecoveryStatus = Literal["recovered", "unresolved", "unknown"]

# High-precision phrase → class. Order matters (first match wins).
_CLASS_PATTERNS: list[tuple[CorrectionClass, re.Pattern[str]]] = [
    (
        "scope_boundary_violation",
        re.compile(
            r"\b(don'?t touch|do not (?:touch|change|modify)|out of scope|"
            r"only (?:change|edit|fix)|leave .+ alone|wrong (?:file|directory|repo))\b",
            re.I,
        ),
    ),
    (
        "instruction_rule_violation",
        re.compile(
            r"\b(follow (?:the )?(?:rules?|instructions?)|you (?:ignored|skipped)|"
            r"as (?:instructed|specified)|per (?:the )?(?:rules?|AGENTS\.md)|"
            r"stop (?:breaking|violating))\b",
            re.I,
        ),
    ),
    (
        "project_reading_failure",
        re.compile(
            r"\b(read (?:the )?(?:code|file|docs?|readme)|you didn'?t read|"
            r"look at (?:the )?(?:existing|current)|wrong (?:api|import|module))\b",
            re.I,
        ),
    ),
    (
        "intent_misunderstanding",
        re.compile(
            r"\b(that'?s not what i (?:asked|meant|wanted)|i (?:said|asked) .+ not |"
            r"you misunderstood|wrong (?:task|goal|interpretation)|not that)\b",
            re.I,
        ),
    ),
    (
        "execution_verification_failure",
        re.compile(
            r"\b(tests? (?:still )?fail|run (?:the )?tests?|typecheck|"
            r"build (?:still )?fail|verify (?:it|this)|lint (?:still )?fail)\b",
            re.I,
        ),
    ),
    (
        "misleading_progress_reporting",
        re.compile(
            r"\b(it'?s not (?:done|fixed|working)|still broken|you said (?:it )?(?:was )?"
            r"(?:done|fixed|working)|false(?:ly)? (?:claimed|reported))\b",
            re.I,
        ),
    ),
    (
        "implementation_failure",
        re.compile(
            r"\b(this (?:still )?doesn'?t work|fix (?:the )?(?:bug|error|regression)|"
            r"broken again|revert (?:that|this)|undo (?:that|this))\b",
            re.I,
        ),
    ),
    (
        "unclassified",
        re.compile(
            r"\b(stop|no[,!]?\s|wrong|incorrect|try again|do not|"
            r"don'?t|never (?:do|use)|instead)\b",
            re.I,
        ),
    ),
]

_SUCCESS_TOOL = re.compile(
    r"\b(pytest|vitest|test|build|typecheck|mypy|ruff|lint)\b",
    re.I,
)


def classify_user_text(text: str) -> tuple[CorrectionClass, str] | None:
    """Return (class, matched_signal) or None when no high-precision hit."""
    cleaned = " ".join(text.split())
    if len(cleaned) < 3:
        return None
    for class_name, pattern in _CLASS_PATTERNS:
        match = pattern.search(cleaned)
        if match is not None:
            return class_name, match.group(0)
    return None


def build_corrections_dict(
    *,
    trace: Trace,
    spans: list[Span],
    relabels: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic corrections ledger for one session."""
    ordered = sorted(spans, key=lambda item: item.seq)
    events: list[dict[str, Any]] = []
    for index, span in enumerate(ordered):
        if span.kind != "user_msg":
            continue
        text = (span.text_inline or "").strip()
        hit = classify_user_text(text)
        if hit is None:
            continue
        class_name, signal = hit
        recovery_status, recovery_span_id = _recovery_after(ordered, index)
        correction_id = _stable_correction_id(trace.trace_id, span.span_id, class_name)
        relabel = (relabels or {}).get(correction_id)
        # User relabels may use free-text classes; keep original_class typed.
        classification: str = class_name
        if relabel is not None and relabel.get("relabel_class"):
            classification = str(relabel["relabel_class"])
        events.append(
            {
                "correction_id": correction_id,
                "span_id": span.span_id,
                "seq": span.seq,
                "classification": classification,
                "original_class": class_name,
                "confidence": "medium" if class_name != "unclassified" else "low",
                "signal": signal,
                "excerpt": text[:240],
                "recovery_status": recovery_status,
                "recovery_span_id": recovery_span_id,
                "user_relabel": relabel,
                "kind": "observed_phrase_match",
            }
        )

    unresolved = sum(1 for item in events if item["recovery_status"] == "unresolved")
    body: dict[str, Any] = {
        "schema_version": CORRECTIONS_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "trace_id": trace.trace_id,
        "correction_count": len(events),
        "unresolved_count": unresolved,
        "corrections": events,
        "limitations": [
            "Classification uses high-precision phrase/sequence signals only.",
            "False negatives are expected; absence of matches is not zero supervision tax.",
            "Recovery linkage is heuristic (later successful verify-like tool) and may be wrong.",
            "Not for employee ranking or cross-user comparison.",
        ],
        "ranking_forbidden": True,
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    body["content_hash"] = digest
    return body


def build_corrections_for_trace(
    conn: sqlite3.Connection,
    trace_id: str,
    *,
    relabels: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    spans = SpanRepo.list_by_trace(conn, trace_id)
    if relabels is None:
        from server.store.repos.corrections import CorrectionRepo

        relabels = CorrectionRepo.list_relabels(conn, trace_id)
    return build_corrections_dict(trace=trace, spans=spans, relabels=relabels)


def _recovery_after(spans: list[Span], correction_index: int) -> tuple[RecoveryStatus, str | None]:
    for span in spans[correction_index + 1 :]:
        if span.kind == "user_msg":
            if classify_user_text(span.text_inline or "") is not None:
                return "unresolved", None
            continue
        if (
            span.kind == "tool_call"
            and span.status == "ok"
            and _SUCCESS_TOOL.search(span.name or "")
        ):
            return "recovered", span.span_id
        if span.kind == "tool_result" and span.status == "ok":
            parent_name = span.name or ""
            if _SUCCESS_TOOL.search(parent_name):
                return "recovered", span.span_id
    return "unknown", None


def _stable_correction_id(trace_id: str, span_id: str, class_name: str) -> str:
    digest = hashlib.sha256(f"{trace_id}:{span_id}:{class_name}".encode()).hexdigest()[:20]
    # Prefer deterministic ids over random ULIDs so relabels survive rebuilds.
    return f"corr_{digest}"


def new_ephemeral_id() -> str:
    return new_ulid()
