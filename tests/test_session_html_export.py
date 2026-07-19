"""Hostile privacy tests for scrubbed session HTML export."""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from server.cli import app
from server.export.session_html import assert_hostile_safe, export_session_html
from server.store.db import connect
from server.store.migrate import migrate
from server.util.ids import new_ulid


def _seed_hostile(root: Path) -> str:
    cairn = root / ".cairn"
    cairn.mkdir(parents=True)
    conn = connect(cairn / "cairn.db")
    migrate(conn)
    ws_id = new_ulid()
    trace_id = "tr-html-1"
    secret = "sk-testSECRETVALUE123456"
    conn.execute(
        "INSERT INTO workspaces (workspace_id, root_path, name, created_at) VALUES (?, ?, ?, ?)",
        (ws_id, str(root), "html-export", datetime.now(UTC).isoformat()),
    )
    conn.execute(
        "INSERT INTO traces (trace_id, workspace_id, source, started_at, status, title, "
        "input_tokens, output_tokens, cost, cost_source, span_count, waste_tokens) "
        "VALUES (?, ?, 'cursor', '2026-07-01T10:00:00Z', 'completed', "
        "'leak https://evil.example/path and /Users/alice/secret-repo/src/a.py', "
        "120, 40, 2.25, 'priced', 2, 10)",
        (trace_id, ws_id),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, text_inline, input_tokens, output_tokens) VALUES "
        "('sp1', ?, NULL, 1, 'user_msg', 'user', 'ok', NULL, ?, 0, 0)",
        (
            trace_id,
            f"Open {root / 'src' / 'private.py'} with token {secret} "
            "and https://evil.example/hook <script>alert(1)</script>",
        ),
    )
    conn.execute(
        "INSERT INTO spans (span_id, trace_id, parent_span_id, seq, kind, name, status, "
        "path_rel, text_inline) VALUES "
        "('sp2', ?, 'sp1', 2, 'tool_call', 'read', 'error', 'src/private.py', "
        "'Bearer abcdEFGH1234 and /tmp/abs/path.py')",
        (trace_id,),
    )
    conn.commit()
    conn.close()
    return trace_id


def test_session_html_is_scrubbed_csp_and_script_free(tmp_path: Path) -> None:
    root = tmp_path / "secret-repo"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "private.py").write_text("print('x')\n", encoding="utf-8")
    trace_id = _seed_hostile(root)
    conn = connect(root / ".cairn" / "cairn.db")
    ws_id = conn.execute("SELECT workspace_id FROM workspaces").fetchone()[0]
    result = export_session_html(
        conn,
        workspace_id=str(ws_id),
        workspace_root=root,
        trace_id=trace_id,
    )
    conn.close()
    assert result["ok"] is True
    path = Path(result["path"])
    document = path.read_text(encoding="utf-8")
    assert_hostile_safe(document)
    assert "Content-Security-Policy" in document
    assert "script-src 'none'" in document
    assert "sk-testSECRETVALUE123456" not in document
    assert "evil.example" not in document
    assert "/Users/alice" not in document
    assert str(root) not in document
    assert "<script>alert(1)</script>" not in document
    assert "onerror=" not in document.lower()
    assert "Waterfall" in document
    assert "Transcript" in document
    assert "Postmortem" in document
    assert "Evidence summary" in document
    assert not re.search(r"https?://", document)
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_cairn_export_session_html_cli(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "ws"
    root.mkdir()
    trace_id = _seed_hostile(root)
    monkeypatch.chdir(root)
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["export", "session", trace_id, "--html", "--workspace", str(root)],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["schema"] == "cairn.session_html.v1"
    document = Path(payload["path"]).read_text(encoding="utf-8")
    assert_hostile_safe(document)

    missing_flag = runner.invoke(
        app,
        ["export", "session", trace_id, "--workspace", str(root)],
    )
    assert missing_flag.exit_code == 2
