"""Deterministic verification receipt v1 coverage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from server.analyze.verification import (
    RECEIPT_SCHEMA_VERSION,
    build_receipt_dict,
    build_receipt_for_trace,
    verification_status_from_fields,
)
from server.api.actions import get_action
from server.api.payloads import build_trace_receipt
from server.cli import app
from server.models.outcome import Outcome
from server.models.span import Span
from server.models.trace import Trace
from server.models.workspace import Workspace
from server.store.db import Database
from server.store.repos.outcomes import OutcomeRepo
from server.store.repos.receipts import ReceiptRepo
from server.store.repos.spans import SpanRepo
from server.store.repos.traces import TraceRepo
from server.store.repos.workspaces import WorkspaceRepo
from server.util.ids import new_ulid


def test_status_mapping_is_honest() -> None:
    assert (
        verification_status_from_fields(
            tests_failed=1,
            build_status="pass",
            tests_run=3,
            outcome_label="success",
            has_outcome=True,
        )
        == "failed"
    )
    assert (
        verification_status_from_fields(
            tests_failed=0,
            build_status="pass",
            tests_run=2,
            outcome_label=None,
            has_outcome=True,
        )
        == "verified"
    )
    assert (
        verification_status_from_fields(
            tests_failed=None,
            build_status=None,
            tests_run=None,
            outcome_label="success",
            has_outcome=True,
        )
        == "debt"
    )
    assert (
        verification_status_from_fields(
            tests_failed=None,
            build_status=None,
            tests_run=None,
            outcome_label=None,
            has_outcome=False,
        )
        == "unknown"
    )


def test_receipt_idempotent_and_claims_empty() -> None:
    trace = Trace(
        trace_id="tr-r1",
        workspace_id="ws",
        source="cursor",
        status="completed",
        input_tokens=10,
        output_tokens=5,
    )
    spans = [
        Span(
            span_id="sp1",
            trace_id="tr-r1",
            seq=1,
            kind="user_msg",
            name="user",
            status="ok",
            text_inline="Fix the failing tests",
        ),
        Span(
            span_id="sp2",
            trace_id="tr-r1",
            seq=2,
            kind="tool_call",
            name="pytest",
            status="error",
        ),
    ]
    outcome = Outcome(trace_id="tr-r1", tests_run=1, tests_failed=1, build_status="fail")
    first = build_receipt_dict(trace=trace, spans=spans, outcome=outcome)
    second = build_receipt_dict(trace=trace, spans=spans, outcome=outcome)
    assert first["content_hash"] == second["content_hash"]
    assert first["schema_version"] == RECEIPT_SCHEMA_VERSION
    assert first["status"] == "failed"
    assert first["claims"] == []
    assert "not extracted" in first["claims_limitation"].lower()
    assert any(component["id"] == "ordering_unproven" for component in first["debt"]["components"])


def _seed(root: Path, *, success_without_checks: bool = False) -> str:
    db = Database(root / ".cairn" / "cairn.db")
    ws_id = new_ulid()
    trace_id = "tr-receipt-1"
    WorkspaceRepo.create(
        db.reader,
        Workspace(
            workspace_id=ws_id,
            root_path=str(root),
            name="receipt",
            created_at=datetime.now(UTC).isoformat(),
        ),
    )
    TraceRepo.create(
        db.reader,
        Trace(
            trace_id=trace_id,
            workspace_id=ws_id,
            source="cursor",
            started_at="2026-07-01T10:00:00Z",
            status="completed",
            title="session",
            span_count=2,
        ),
    )
    SpanRepo.create(
        db.reader,
        Span(
            span_id="sp1",
            trace_id=trace_id,
            seq=1,
            kind="user_msg",
            name="user",
            status="ok",
            text_inline="Ship the fix",
        ),
    )
    SpanRepo.create(
        db.reader,
        Span(
            span_id="sp2",
            trace_id=trace_id,
            seq=2,
            kind="tool_call",
            name="vitest",
            status="ok",
        ),
    )
    if success_without_checks:
        OutcomeRepo.upsert(
            db.reader,
            Outcome(trace_id=trace_id, outcome_label="success"),
        )
    else:
        OutcomeRepo.upsert(
            db.reader,
            Outcome(
                trace_id=trace_id,
                tests_run=4,
                tests_passed=4,
                tests_failed=0,
                build_status="pass",
                outcome_label="success",
            ),
        )
    db.reader.commit()
    db.close()
    return trace_id


def test_api_payload_and_rebuild_persist(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    trace_id = _seed(root)
    db = Database(root / ".cairn" / "cairn.db")
    payload = build_trace_receipt(db.reader, trace_id)
    assert payload is not None
    assert payload.status == "verified"
    assert payload.persisted is False
    receipt = build_receipt_for_trace(db.reader, trace_id)
    assert receipt is not None
    ReceiptRepo.upsert(db.reader, receipt, built_at="2026-07-01T12:00:00Z")
    db.reader.commit()
    again = build_trace_receipt(db.reader, trace_id)
    assert again is not None
    assert again.persisted is True
    assert again.content_hash == receipt["content_hash"]
    db.close()


def test_debt_success_without_checks(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    trace_id = _seed(root, success_without_checks=True)
    db = Database(root / ".cairn" / "cairn.db")
    payload = build_trace_receipt(db.reader, trace_id)
    db.close()
    assert payload is not None
    assert payload.status == "debt"
    active = {item.id for item in payload.debt.components if item.active}
    assert "success_without_checks" in active
    assert "missing_tests" in active


def test_cairn_receipt_cli_and_action(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".cairn").mkdir()
    trace_id = _seed(root)
    monkeypatch.chdir(root)
    runner = CliRunner()
    result = runner.invoke(app, ["receipt", trace_id, "--json", "--workspace", str(root)])
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert body["schema"] == "cairn.receipt.v1"
    assert body["status"] == "verified"
    assert body["claims"] == []

    action = get_action("verification_rebuild")
    assert action is not None
    from server.cli import _make_ctx

    ctx = _make_ctx(root)
    out = action.handler(
        action.params_model.model_validate({"trace_id": trace_id}),
        ctx,
    )
    assert out["ok"] is True
    assert out["rebuilt"] == 1
