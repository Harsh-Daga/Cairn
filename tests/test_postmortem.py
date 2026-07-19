"""Deterministic diagnose-based postmortems."""

from __future__ import annotations

from server.analyze.postmortem import build_postmortem
from server.models.outcome import Diagnostic, Outcome
from server.models.span import Span
from server.models.trace import Trace


def _span(
    *,
    span_id: str,
    seq: int,
    kind: str = "tool_call",
    name: str = "pytest",
    status: str = "ok",
    waste_category: str | None = None,
    waste_tokens: int = 0,
) -> Span:
    return Span(
        span_id=span_id,
        trace_id="t1",
        seq=seq,
        kind=kind,  # type: ignore[arg-type]
        name=name,
        status=status,
        waste_category=waste_category,
        waste_tokens=waste_tokens,
    )


def test_build_postmortem_from_diagnose_and_errors() -> None:
    trace = Trace(
        trace_id="t1",
        workspace_id="ws",
        source="codex",
        external_id="t1",
        status="failed",
        input_tokens=10_000,
        output_tokens=1_000,
        cost=2.0,
        cost_source="observed",
    )
    spans = [
        _span(span_id="s1", seq=1, kind="user_msg", name="ask"),
        _span(span_id="s2", seq=2, status="error", waste_category="retry_loop", waste_tokens=400),
        _span(span_id="s3", seq=3, status="error", waste_category="blind_retry", waste_tokens=600),
    ]
    diagnostic = Diagnostic(
        trace_id="t1",
        failure_origin_span_id="s2",
        failure_signature="error_waste_spike:2.00",
        primary_category="tool_failure",
        cascade_root_span_id="s2",
        cascade_blast_tokens=1000,
    )
    outcome = Outcome(trace_id="t1", outcome_label="failed", quality_score=30.0)
    postmortem = build_postmortem(trace=trace, spans=spans, diagnostic=diagnostic, outcome=outcome)
    assert postmortem is not None
    assert postmortem["source"] == "diagnose_cascade"
    assert postmortem["reflector"] is None
    assert len(postmortem["steps"]) == 4
    assert "Markdown" not in postmortem["markdown"]
    assert "# Cairn postmortem" in postmortem["markdown"]
    assert postmortem["span_links"]
    assert any(
        "causal" in note.lower() or "localization" in note.lower()
        for note in postmortem["uncertainty"]
    )


def test_build_postmortem_skips_healthy_sessions() -> None:
    trace = Trace(
        trace_id="t2",
        workspace_id="ws",
        source="codex",
        external_id="t2",
        status="completed",
        cost_source="absent",
    )
    spans = [_span(span_id="ok1", seq=1, status="ok")]
    outcome = Outcome(trace_id="t2", outcome_label="success", quality_score=90.0)
    assert build_postmortem(trace=trace, spans=spans, diagnostic=None, outcome=outcome) is None


def test_trace_detail_includes_postmortem(api_client, api_workspace: tuple) -> None:
    _root, _workspace_id, trace_id = api_workspace
    detail = api_client.get(f"/api/traces/{trace_id}").json()
    # Demo/fixture session may or may not be eligible; ensure field is present.
    assert "postmortem" in detail
    if detail["postmortem"] is not None:
        assert detail["postmortem"]["markdown"]
        assert detail["postmortem"]["limitation"]
        pm = api_client.get(f"/api/traces/{trace_id}/postmortem")
        assert pm.status_code == 200
        assert pm.json()["trace_id"] == trace_id
