"""Phase 5 — rewind suggestion and primer cost warning."""

from __future__ import annotations

import sqlite3
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cairn.ledger.schema import migrate
from cairn.mcp.tools import ToolsContext, _project_primer
from cairn.outcomes.git import commit_before_timestamp
from cairn.render.session_payload import session_payload


def _git_commit(repo: Path, msg: str) -> str:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", msg], cwd=repo, check=True, capture_output=True)
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    )
    return r.stdout.strip()


def test_commit_before_timestamp(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "a.txt").write_text("1", encoding="utf-8")
    good = _git_commit(repo, "good")
    future = "2099-01-01T00:00:00+00:00"
    sha = commit_before_timestamp(str(repo), future)
    assert sha == good


def test_session_rewind_suggestion(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
    (repo / "f.txt").write_text("x", encoding="utf-8")
    good = _git_commit(repo, "baseline")
    now = datetime.now(UTC).isoformat()

    db = repo / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, cwd, project, started_at, status,
          total_input_tokens, total_output_tokens, has_cost, event_count
        ) VALUES ('r1', 'claude-code', 'e1', ?, 'repo', ?, 'completed', 100, 20, 1, 3)
        """,
        (str(repo), now),
    )
    conn.execute(
        "INSERT INTO events (run_id, seq, type, role, ts) "
        "VALUES ('r1', 1, 'user_prompt', 'user', ?)",
        (now,),
    )
    conn.execute(
        "INSERT INTO events (run_id, seq, type, role, ts, event_id) "
        "VALUES ('r1', 2, 'tool_call', 'assistant', ?, 2)",
        (now,),
    )
    conn.execute(
        """
        INSERT INTO diagnostics (
          run_id, outcome_label, label_source, cascade_root_event_id,
          cascade_blast_tokens, ideal_path_savings_tokens, computed_at
        ) VALUES ('r1', 'partial', 'deterministic', 2, 500, 0, ?)
        """,
        (now,),
    )
    conn.commit()
    payload = session_payload(conn, run_id="r1")
    conn.close()
    rewind = payload.get("rewind_suggestion")
    assert rewind is not None
    assert rewind["commit_sha"] == good
    assert "git reset --hard" in rewind["command"]


def test_primer_cost_warning_when_above_p95(tmp_path: Path) -> None:
    w = tmp_path / "proj"
    w.mkdir()
    db = w / ".cairn" / "ledger.db"
    db.parent.mkdir()
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    conn.execute(
        """
        INSERT INTO expectation_baselines (
          model, difficulty_bucket, metric, mean, stdev, n, updated_at
        ) VALUES ('unknown', 'standard', 'total_tokens', 100, 10, 6, '2026-01-01')
        """
    )
    conn.commit()
    ctx = ToolsContext(conn=conn, project_root=w, project_name=w.name)
    long_task = "x" * 500
    out = _project_primer(ctx, {"project": w.name, "task": long_task})
    assert out.get("cost_warning")
