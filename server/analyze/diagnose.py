"""Failure localization + cascade analysis view."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from cairn.outcomes.labels import derive_outcome_label
from server.analyze.diagnose_cascade import detect_cascade
from server.analyze.diagnose_ideal import ideal_path_savings
from server.analyze.diagnose_localize import localize_failure
from server.analyze.diagnose_taxonomy import classify_failure
from server.analyze.events import spans_to_events
from server.analyze.views import IncrementalView, trace_input_hash
from server.models.outcome import Diagnostic, Outcome
from server.models.span import Span
from server.models.trace import Trace
from server.store.repos.diagnostics import DiagnosticRepo
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.util.hash import hash_obj


def compute_diagnostics(
    trace: Trace,
    spans: list[Span],
    outcome_row: Outcome | None = None,
) -> Diagnostic:
    """Compute one diagnostic model from trace/spans/outcome inputs."""
    events = spans_to_events(spans)
    seq_to_span_id = {span.seq: span.span_id for span in spans}
    status = str(trace.status or "completed")
    git_landed = bool(outcome_row.commit_landed) if outcome_row else False
    tests_passed = outcome_row.tests_passed if outcome_row else None
    tests_failed = outcome_row.tests_failed if outcome_row else None

    outcome_label, _ = derive_outcome_label(
        git_landed=git_landed,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        status=status,
        events=events,
    )
    origin_seq, signature, _one_liner = localize_failure(events)
    if outcome_label == "landed":
        origin_seq = None
        signature = None

    cascade_root_seq, _blast_events, blast_tokens = detect_cascade(events)
    savings, _ideal = ideal_path_savings(events)
    primary, secondary = classify_failure(
        events,
        outcome_label=outcome_label,
        failure_signature=signature,
    )

    return Diagnostic(
        trace_id=trace.trace_id,
        failure_origin_span_id=seq_to_span_id.get(origin_seq) if origin_seq is not None else None,
        failure_signature=signature,
        primary_category=primary,
        secondary_category=secondary,
        cascade_root_span_id=seq_to_span_id.get(cascade_root_seq)
        if cascade_root_seq is not None
        else None,
        cascade_blast_tokens=blast_tokens or None,
        ideal_path_savings_tokens=savings,
        computed_at=datetime.now(UTC).isoformat(),
    )


class DiagnoseView(IncrementalView):
    """Compute and persist diagnostics per trace."""

    view_name = "diagnose"
    VERSION = 1

    def keys_for(self, trace_id: str) -> list[str]:
        return [trace_id]

    def input_hash_for(self, conn: sqlite3.Connection, key: str) -> str:
        outcome = OutcomeRepo.get(conn, key)
        return hash_obj(
            {
                "trace_hash": trace_input_hash(conn, key),
                "outcome": {
                    "commit_landed": outcome.commit_landed if outcome else None,
                    "tests_passed": outcome.tests_passed if outcome else None,
                    "tests_failed": outcome.tests_failed if outcome else None,
                },
            }
        )

    def compute(self, conn: sqlite3.Connection, key: str) -> None:
        trace = TraceRepo.get(conn, key)
        if trace is None:
            return
        spans = SpanRepo.list_by_trace(conn, key)
        outcome = OutcomeRepo.get(conn, key)
        diagnostic = compute_diagnostics(trace, spans, outcome)
        DiagnosticRepo.upsert(conn, diagnostic)


__all__ = ["DiagnoseView", "compute_diagnostics"]
