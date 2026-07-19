"""Corrections classifier, relabel, and handoff capsule coverage."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from server.analyze.corrections import build_corrections_for_trace, classify_user_text
from server.analyze.handoff import build_handoff_for_trace
from server.api.actions import get_action
from server.cli import app
from server.store.db import connect
from server.store.migrate import migrate
from server.store.repos.corrections import CorrectionRepo
from server.util.ids import new_ulid


def _seed(root: Path) -> tuple[str, str]:
    cairn = root / ".cairn"
    cairn.mkdir(parents=True)
    conn = connect(cairn / "cairn.db")
    migrate(conn)
    ws_id = new_ulid()
    trace_id = "tr-corr-1"
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws_id, str(root), "corr", datetime.now(UTC).isoformat()),
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
        "VALUES (?, ?, 'cursor', '2026-07-01T10:00:00Z', 'completed', 'fix', "
        "100, 40, 1.5, 'priced', 4, 5)",
        (trace_id, ws_id),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "text_inline) VALUES "
        "('sp1', ?, NULL, 1, 'user_msg', 'user', 'ok', 'Please fix the failing tests'),"
        "('sp2', ?, 'sp1', 2, 'tool_call', 'edit', 'ok', NULL),"
        "('sp3', ?, NULL, 3, 'user_msg', 'user', 'ok', "
        "'That''s not what I asked — you misunderstood the goal'),"
        "('sp4', ?, 'sp3', 4, 'tool_call', 'pytest', 'ok', NULL)",
        (trace_id, trace_id, trace_id, trace_id),
    )
    conn.execute(
        "INSERT INTO outcomes (trace_id, tests_run, tests_passed, tests_failed, "
        "build_status, outcome_label, files_changed_json, captured_at) "
        "VALUES (?, 2, 2, 0, 'pass', 'success', ?, ?)",
        (trace_id, json.dumps(["src/a.py"]), datetime.now(UTC).isoformat()),
    )
    conn.commit()
    conn.close()
    return ws_id, trace_id


def test_classifier_is_conservative() -> None:
    assert classify_user_text("hello there") is None
    hit = classify_user_text("That's not what I asked — you misunderstood")
    assert hit is not None
    assert hit[0] == "intent_misunderstanding"


def test_corrections_recovery_and_relabel(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _ws_id, trace_id = _seed(root)
    conn = connect(root / ".cairn" / "cairn.db")
    payload = build_corrections_for_trace(conn, trace_id)
    assert payload is not None
    assert payload["correction_count"] >= 1
    event = payload["corrections"][0]
    assert event["classification"] == "intent_misunderstanding"
    assert event["recovery_status"] == "recovered"
    assert payload["ranking_forbidden"] is True

    CorrectionRepo.upsert_relabel(
        conn,
        correction_id=event["correction_id"],
        trace_id=trace_id,
        original_class=event["original_class"],
        relabel_class="not_a_correction",
        note="false positive",
        labeled_at=datetime.now(UTC).isoformat(),
    )
    conn.commit()
    relabeled = build_corrections_for_trace(conn, trace_id)
    assert relabeled is not None
    assert relabeled["corrections"][0]["classification"] == "not_a_correction"
    conn.close()


def test_handoff_distinguishes_kinds_and_scrubs(tmp_path: Path) -> None:
    root = tmp_path / "secret-repo"
    root.mkdir()
    _ws_id, trace_id = _seed(root)
    conn = connect(root / ".cairn" / "cairn.db")
    capsule = build_handoff_for_trace(conn, trace_id, workspace_root=root)
    conn.close()
    assert capsule is not None
    kinds = {item["kind"] for section in capsule["sections"] for item in section["items"]}
    assert "fact" in kinds
    assert "recommendation" in kinds
    assert str(root) not in (capsule.get("markdown") or "")
    assert capsule["schema_version"] == "cairn.handoff.v1"


def test_cli_handoff_and_action(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    _ws_id, trace_id = _seed(root)
    runner = CliRunner()
    result = runner.invoke(app, ["handoff", trace_id, "--workspace", str(root), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "cairn.handoff.v1"
    assert get_action("corrections_rebuild") is not None
