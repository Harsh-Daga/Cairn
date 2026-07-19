"""Offline handoff capsules with fact / inference / recommendation tagging."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, Literal

from server.analyze.corrections import build_corrections_for_trace
from server.analyze.verification import build_receipt_for_trace
from server.export.scrub import scrub_text
from server.models.outcome import Outcome
from server.models.span import Span
from server.models.trace import Trace
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo

HANDOFF_SCHEMA_VERSION = "cairn.handoff.v1"
BUILDER_VERSION = "handoff-v1"
DEFAULT_CHAR_BUDGET = 3500

StatementKind = Literal["fact", "inference", "recommendation"]


def build_handoff_dict(
    *,
    trace: Trace,
    spans: list[Span],
    outcome: Outcome | None,
    receipt: dict[str, Any] | None,
    corrections: dict[str, Any] | None,
    workspace_root: Path,
    char_budget: int = DEFAULT_CHAR_BUDGET,
) -> dict[str, Any]:
    """Build a compact continuation capsule. Never calls a provider."""
    ordered = sorted(spans, key=lambda item: item.seq)
    intent = _intent(ordered, receipt, workspace_root)
    errors = [
        {
            "kind": "fact",
            "text": scrub_text(f"{span.name or 'tool'}: {span.status}", workspace_root),
            "span_id": span.span_id,
        }
        for span in ordered
        if span.status == "error"
    ][:8]
    files = _files(outcome, ordered, workspace_root)
    tools = [
        {
            "kind": "fact",
            "text": scrub_text(span.name or "tool", workspace_root),
            "span_id": span.span_id,
        }
        for span in ordered
        if span.kind == "tool_call"
    ][:12]
    decisions = _assistant_decisions(ordered, workspace_root)
    correction_notes = _correction_notes(corrections)
    debt = _debt_notes(receipt)
    next_checks = _next_checks(receipt, outcome, corrections)

    sections = [
        {"id": "goal", "title": "Current goal", "items": [intent]},
        {
            "id": "decisions",
            "title": "Decisions already made",
            "items": decisions or [_stmt("inference", "No durable decisions were extracted.")],
        },
        {
            "id": "blockers",
            "title": "Exact blockers / errors",
            "items": errors or [_stmt("fact", "No error-status spans were recorded.")],
        },
        {"id": "files", "title": "Files changed / touched", "items": files},
        {
            "id": "tools",
            "title": "Commands / tools observed",
            "items": tools or [_stmt("fact", "No tool_call spans were recorded.")],
        },
        {
            "id": "tests",
            "title": "Tests / build results",
            "items": [_tests(outcome)],
        },
        {
            "id": "corrections",
            "title": "User corrections",
            "items": correction_notes,
        },
        {
            "id": "verification_debt",
            "title": "Verification debt",
            "items": debt,
        },
        {
            "id": "next",
            "title": "Recommended next checks",
            "items": next_checks,
        },
        {
            "id": "budget",
            "title": "Token / cost context",
            "items": [
                _stmt(
                    "fact",
                    (
                        f"Recorded tokens in={trace.input_tokens} out={trace.output_tokens}; "
                        f"cost={trace.cost if trace.cost is not None else 'unavailable'} "
                        f"({trace.cost_source or 'unknown'})."
                    ),
                )
            ],
        },
    ]

    trimmed, truncated = _trim_sections(sections, char_budget)
    body: dict[str, Any] = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "builder_version": BUILDER_VERSION,
        "trace_id": trace.trace_id,
        "char_budget": char_budget,
        "truncated": truncated,
        "sections": trimmed,
        "limitations": [
            "Deterministic extraction only; optional LLM enrichment is not applied.",
            "Sensitive paths and secrets are scrubbed; raw transcript is omitted.",
            "fact = recorded ledger field; inference = heuristic; recommendation = next check.",
        ],
    }
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    body["content_hash"] = digest
    body["markdown"] = render_handoff_markdown(body)
    # markdown excluded from hash stability — recompute hash without it for idempotence
    return body


def build_handoff_for_trace(
    conn: sqlite3.Connection,
    trace_id: str,
    *,
    workspace_root: Path,
    char_budget: int = DEFAULT_CHAR_BUDGET,
) -> dict[str, Any] | None:
    trace = TraceRepo.get(conn, trace_id)
    if trace is None:
        return None
    spans = SpanRepo.list_by_trace(conn, trace_id)
    outcome = OutcomeRepo.get(conn, trace_id)
    receipt = build_receipt_for_trace(conn, trace_id)
    corrections = build_corrections_for_trace(conn, trace_id)
    return build_handoff_dict(
        trace=trace,
        spans=spans,
        outcome=outcome,
        receipt=receipt,
        corrections=corrections,
        workspace_root=workspace_root,
        char_budget=char_budget,
    )


def render_handoff_markdown(capsule: dict[str, Any]) -> str:
    lines = [
        f"# Handoff · {capsule['trace_id']}",
        "",
        (
            f"Schema `{capsule['schema_version']}` · "
            f"hash `{str(capsule.get('content_hash', ''))[:16]}`"
        ),
        "",
    ]
    for section in capsule.get("sections") or []:
        lines.append(f"## {section['title']}")
        for item in section.get("items") or []:
            kind = item.get("kind", "fact")
            text = item.get("text", "")
            cite = item.get("span_id")
            suffix = f" _(span {cite})_" if cite else ""
            lines.append(f"- **{kind}**: {text}{suffix}")
        lines.append("")
    for note in capsule.get("limitations") or []:
        lines.append(f"_Limitation: {note}_")
    return "\n".join(lines).strip() + "\n"


def _stmt(kind: StatementKind, text: str, span_id: str | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"kind": kind, "text": text}
    if span_id:
        item["span_id"] = span_id
    return item


def _intent(
    spans: list[Span],
    receipt: dict[str, Any] | None,
    workspace_root: Path,
) -> dict[str, Any]:
    if receipt and receipt.get("intent", {}).get("present"):
        summary = scrub_text(str(receipt["intent"].get("summary") or ""), workspace_root)
        return _stmt("fact", summary, receipt["intent"].get("span_id"))
    for span in spans:
        if span.kind == "user_msg" and span.text_inline:
            return _stmt(
                "fact",
                scrub_text(span.text_inline, workspace_root)[:400],
                span.span_id,
            )
    return _stmt("inference", "Original user goal was not retained in the ledger.")


def _files(
    outcome: Outcome | None, spans: list[Span], workspace_root: Path
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if outcome and outcome.files_changed:
        for path in outcome.files_changed[:12]:
            items.append(_stmt("fact", scrub_text(str(path), workspace_root)))
    else:
        seen: set[str] = set()
        for span in spans:
            if span.path_rel and span.path_rel not in seen:
                seen.add(span.path_rel)
                items.append(_stmt("fact", scrub_text(span.path_rel, workspace_root), span.span_id))
            if len(items) >= 12:
                break
    if not items:
        items.append(_stmt("fact", "No file paths were recorded on the outcome or spans."))
    return items


def _assistant_decisions(spans: list[Span], workspace_root: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for span in spans:
        if span.kind != "assistant_msg" or not span.text_inline:
            continue
        text = scrub_text(span.text_inline, workspace_root)
        if len(text) < 20:
            continue
        items.append(_stmt("inference", text[:220], span.span_id))
        if len(items) >= 4:
            break
    return items


def _tests(outcome: Outcome | None) -> dict[str, Any]:
    if outcome is None:
        return _stmt("fact", "No outcome row was recorded.")
    return _stmt(
        "fact",
        (
            f"label={outcome.outcome_label or 'none'}; "
            f"tests_run={outcome.tests_run}; passed={outcome.tests_passed}; "
            f"failed={outcome.tests_failed}; build={outcome.build_status or 'none'}"
        ),
    )


def _correction_notes(corrections: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not corrections or not corrections.get("corrections"):
        return [_stmt("fact", "No high-precision correction phrases were classified.")]
    items: list[dict[str, Any]] = []
    for event in corrections["corrections"][:8]:
        items.append(
            _stmt(
                "fact",
                (
                    f"{event['classification']} ({event['recovery_status']}) "
                    f"signal={event['signal']!r}"
                ),
                event.get("span_id"),
            )
        )
    return items


def _debt_notes(receipt: dict[str, Any] | None) -> list[dict[str, Any]]:
    if receipt is None:
        return [_stmt("fact", "Verification receipt unavailable.")]
    active = [c for c in receipt.get("debt", {}).get("components", []) if c.get("active")]
    if not active:
        return [
            _stmt(
                "fact",
                f"Receipt status={receipt.get('status')}; no active debt components.",
            )
        ]
    return [
        _stmt(
            "fact",
            f"{component['id']}: {component.get('reason', '')}",
        )
        for component in active[:6]
    ]


def recommended_next_checks(
    receipt: dict[str, Any] | None,
    outcome: Outcome | None,
    corrections: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Public alias used by MCP/CLI next-evidence previews."""
    return _next_checks(receipt, outcome, corrections)


def _next_checks(
    receipt: dict[str, Any] | None,
    outcome: Outcome | None,
    corrections: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    if outcome is None or outcome.tests_run is None:
        checks.append(
            _stmt(
                "recommendation",
                "Run the project’s recorded test command and capture pass/fail in the ledger.",
            )
        )
    if outcome is None or outcome.build_status is None:
        checks.append(
            _stmt(
                "recommendation",
                "Record a build/typecheck result before treating the change as verified.",
            )
        )
    if corrections and corrections.get("unresolved_count", 0) > 0:
        checks.append(
            _stmt(
                "recommendation",
                "Re-read unresolved user corrections and confirm each was addressed.",
            )
        )
    if receipt and receipt.get("status") in {"debt", "unverified", "unknown"}:
        checks.append(
            _stmt(
                "recommendation",
                "Close verification debt items listed on the receipt before handoff.",
            )
        )
    if not checks:
        checks.append(
            _stmt(
                "recommendation",
                "Spot-check the highest-risk changed path and confirm acceptance criteria.",
            )
        )
    return checks[:5]


def _trim_sections(
    sections: list[dict[str, Any]], budget: int
) -> tuple[list[dict[str, Any]], bool]:
    used = 0
    out: list[dict[str, Any]] = []
    truncated = False
    for section in sections:
        items: list[dict[str, Any]] = []
        for item in section["items"]:
            cost = len(str(item.get("text") or "")) + 24
            if used + cost > budget and items:
                truncated = True
                break
            if used + cost > budget:
                truncated = True
                break
            items.append(item)
            used += cost
        out.append({**section, "items": items})
        if truncated:
            # Keep remaining section headers with empty items omitted for clarity.
            break
    return out, truncated
