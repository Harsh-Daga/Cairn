"""Regression artifact create/validate/export/import (no command execution)."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from server.api.actions import get_action
from server.cli import app
from server.regression.create import create_regression_from_trace
from server.regression.io import export_regression_zip, import_regression_zip
from server.regression.schema import REGRESSION_SCHEMA_VERSION
from server.regression.store import list_regressions, load_regression
from server.regression.validate import validate_artifact
from server.store.db import connect
from server.store.migrate import migrate
from server.util.ids import new_ulid


def _seed(root: Path) -> tuple[str, str]:
    cairn = root / ".cairn"
    cairn.mkdir(parents=True)
    conn = connect(cairn / "cairn.db")
    migrate(conn)
    ws_id = new_ulid()
    trace_id = "tr-reg-1"
    secret = "sk-testSECRETVALUE123456"
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws_id, str(root), "reg", datetime.now(UTC).isoformat()),
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "git_commit, input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
        "VALUES (?, ?, 'cursor', '2026-07-01T10:00:00Z', 'completed', 'fix tests', "
        "'abc123def456', 100, 40, 1.5, 'priced', 3, 5)",
        (trace_id, ws_id),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, text_inline) VALUES "
        "('sp1', ?, NULL, 1, 'user_msg', 'user', 'ok', NULL, ?)",
        (
            trace_id,
            f"Fix pytest failure in {root / 'src' / 'a.py'} token {secret}",
        ),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, text_inline) VALUES "
        "('sp2', ?, 'sp1', 2, 'tool_call', 'pytest tests/test_a.py', 'error', "
        "'tests/test_a.py', 'FAILED')",
        (trace_id,),
    )
    conn.execute(
        "INSERT INTO outcomes (trace_id, commit_sha, commit_landed, files_changed_json, "
        "tests_run, tests_passed, tests_failed, build_status, outcome_label, captured_at) "
        "VALUES (?, 'abc123def456', 0, ?, 2, 1, 1, 'fail', 'failure', ?)",
        (
            trace_id,
            json.dumps(["src/a.py", "tests/test_a.py"]),
            datetime.now(UTC).isoformat(),
        ),
    )
    conn.execute(
        "INSERT INTO diagnostics (trace_id, failure_signature, primary_category, computed_at) "
        "VALUES (?, 'assert_eq', 'test_failure', ?)",
        (trace_id, datetime.now(UTC).isoformat()),
    )
    conn.commit()
    conn.close()
    return ws_id, trace_id


def test_create_round_trip_and_honesty(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "src").mkdir()
    ws_id, trace_id = _seed(root)
    conn = connect(root / ".cairn" / "cairn.db")
    result = create_regression_from_trace(
        conn,
        workspace_root=root,
        workspace_id=ws_id,
        trace_id=trace_id,
    )
    conn.close()
    assert result["ok"] is True
    assert result["schema"] == REGRESSION_SCHEMA_VERSION
    artifact = load_regression(root, result["regression_id"])
    assert artifact is not None
    assert artifact.setup_commands == []
    assert artifact.runs == []
    assert any(c.source == "inferred" for c in artifact.verification_commands)
    assert "sk-test" not in (artifact.scrubbed_task or "")
    assert str(root) not in (artifact.scrubbed_task or "")
    assert artifact.expected_outcome.failure_signature == "assert_eq"
    report = validate_artifact(artifact)
    assert report["ok"] is True
    assert report["executed_commands"] is False
    assert list_regressions(root)


def test_export_import_and_zip_slip_rejected(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    ws_id, trace_id = _seed(root)
    conn = connect(root / ".cairn" / "cairn.db")
    created = create_regression_from_trace(
        conn,
        workspace_root=root,
        workspace_id=ws_id,
        trace_id=trace_id,
    )
    conn.close()
    zip_path = tmp_path / "reg.zip"
    exported = export_regression_zip(root, created["regression_id"], output=zip_path)
    assert exported["ok"] is True

    dest = tmp_path / "other"
    dest.mkdir()
    (dest / ".cairn").mkdir()
    imported = import_regression_zip(dest, zip_path)
    assert imported["ok"] is True
    assert load_regression(dest, imported["regression_id"]) is not None

    hostile = tmp_path / "hostile.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("../escape.json", '{"evil": true}')
        zf.writestr("regression.json", json.dumps({"schema_version": "x"}))
    hostile.write_bytes(buf.getvalue())
    rejected = import_regression_zip(dest, hostile)
    assert rejected["ok"] is False


def test_cli_regression_create_ls_validate(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    _ws_id, trace_id = _seed(root)
    runner = CliRunner()
    create = runner.invoke(
        app,
        ["regression", "create", trace_id, "--workspace", str(root), "--json"],
    )
    assert create.exit_code == 0, create.output
    payload = json.loads(create.output)
    assert payload["schema"] == REGRESSION_SCHEMA_VERSION
    rid = payload["regression_id"]

    listed = runner.invoke(app, ["regression", "ls", "--workspace", str(root), "--json"])
    assert listed.exit_code == 0
    assert rid in listed.output

    validated = runner.invoke(
        app, ["regression", "validate", rid, "--workspace", str(root), "--json"]
    )
    assert validated.exit_code == 0
    report = json.loads(validated.output)
    assert report["ok"] is True
    assert report["executed_commands"] is False


def test_regression_actions_registered() -> None:
    for name in (
        "regression_create",
        "regression_delete",
        "regression_export",
        "regression_import",
        "regression_run",
        "regression_compare",
    ):
        assert get_action(name) is not None


def test_record_run_and_compare_without_execution(tmp_path: Path) -> None:
    from server.regression.compare import compare_regression
    from server.regression.run import record_run_from_trace

    root = tmp_path / "workspace"
    root.mkdir()
    ws_id, trace_id = _seed(root)
    conn = connect(root / ".cairn" / "cairn.db")
    created = create_regression_from_trace(
        conn,
        workspace_root=root,
        workspace_id=ws_id,
        trace_id=trace_id,
    )
    definition_hash = created["content_hash"]
    recorded = record_run_from_trace(
        conn,
        workspace_root=root,
        workspace_id=ws_id,
        regression_id=created["regression_id"],
        trace_id=trace_id,
    )
    assert recorded["ok"] is True
    assert recorded["executed_commands"] is False
    artifact = load_regression(root, created["regression_id"])
    assert artifact is not None
    assert len(artifact.runs) == 1
    assert artifact.runs[0].executed_commands is False
    assert artifact.content_hash == definition_hash

    matched = compare_regression(root, regression_id=created["regression_id"])
    assert matched["ok"] is True
    assert matched["verdict"] == "match"
    assert matched["executed_commands"] is False

    other = "tr-reg-2"
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "git_commit, input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
        "VALUES (?, ?, 'cursor', '2026-07-02T10:00:00Z', 'completed', 'fix again', "
        "'abc123def456', 100, 40, 1.5, 'priced', 1, 5)",
        (other, ws_id),
    )
    conn.execute(
        "INSERT INTO outcomes (trace_id, commit_sha, commit_landed, files_changed_json, "
        "tests_run, tests_passed, tests_failed, build_status, outcome_label, captured_at) "
        "VALUES (?, 'abc123def456', 0, ?, 2, 2, 0, 'pass', 'success', ?)",
        (other, json.dumps(["src/a.py"]), datetime.now(UTC).isoformat()),
    )
    conn.commit()
    second = record_run_from_trace(
        conn,
        workspace_root=root,
        workspace_id=ws_id,
        regression_id=created["regression_id"],
        trace_id=other,
    )
    conn.close()
    assert second["ok"] is True
    mismatched = compare_regression(
        root,
        regression_id=created["regression_id"],
        run_id=second["run_id"],
    )
    assert mismatched["verdict"] == "mismatch"

    runner = CliRunner()
    cli_compare = runner.invoke(
        app,
        [
            "regression",
            "compare",
            created["regression_id"],
            "--workspace",
            str(root),
            "--json",
        ],
    )
    assert cli_compare.exit_code == 0, cli_compare.output
    assert json.loads(cli_compare.output)["ok"] is True
