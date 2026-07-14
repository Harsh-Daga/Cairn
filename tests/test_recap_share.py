"""Privacy and output tests for Agent Wrapped cards."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from server.recap_share import build_share_card_data, render_share_card


def test_share_card_redacts_paths_commands_and_repo_by_default(
    api_workspace: tuple[Path, str, str], tmp_path: Path
) -> None:
    root, workspace_id, trace_id = api_workspace
    secret_path = "clients/secret-acquisition/strategy.py"
    secret_command = "pytest clients/secret-acquisition/test_strategy.py"
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("UPDATE traces SET started_at = ? WHERE trace_id = ?", (now, trace_id))
        for seq in range(100, 103):
            conn.execute(
                """INSERT INTO spans (
                     span_id, trace_id, seq, kind, name, status, path_rel
                   ) VALUES (?, ?, ?, 'tool_call', 'read', 'ok', ?)""",
                (f"private-read-{seq}", trace_id, seq, secret_path),
            )
        for seq in range(103, 108):
            conn.execute(
                """INSERT INTO spans (span_id, trace_id, seq, kind, name, status)
                   VALUES (?, ?, ?, 'tool_call', ?, 'error')""",
                (f"private-failure-{seq}", trace_id, seq, secret_command),
            )
        conn.execute(
            """UPDATE fingerprints SET read_write_ratio = 5, retry_rate = 0.3
               WHERE trace_id = ?""",
            (trace_id,),
        )
        data = build_share_card_data(conn, workspace_id=workspace_id)

    assert data.repo_name is None
    assert data.reread_label == "a Python file"
    assert data.reread_count == 3
    assert data.failure_pattern == "Ran the same failing command 5 times"
    assert data.archetype == "The Anxious Re-reader"
    assert secret_path not in repr(data)
    assert secret_command not in repr(data)

    png_path, svg_path = render_share_card(data, tmp_path / "wrapped.png")
    svg = svg_path.read_text(encoding="utf-8")
    assert secret_path not in svg
    assert secret_command not in svg
    assert root.name not in svg
    assert png_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    with Image.open(png_path) as image:
        assert image.size == (1200, 630)


def test_share_card_repo_name_is_explicit_opt_in(
    api_workspace: tuple[Path, str, str], tmp_path: Path
) -> None:
    root, workspace_id, trace_id = api_workspace
    with sqlite3.connect(root / ".cairn" / "cairn.db") as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            "UPDATE traces SET started_at = ? WHERE trace_id = ?",
            (datetime.now(UTC).isoformat(), trace_id),
        )
        data = build_share_card_data(conn, workspace_id=workspace_id, repo_name="Opt In Repo")
    _png, svg_path = render_share_card(data, tmp_path / "opt-in.png")
    assert "Opt In Repo" in svg_path.read_text(encoding="utf-8")
