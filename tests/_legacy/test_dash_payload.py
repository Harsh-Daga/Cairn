"""Golden-shape tests for v3 dash_payload builders."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from cairn.ledger.schema import migrate
from cairn.render.dash_payload import (
    charts_payload,
    optimize_payload,
    overview_payload,
    search_payload,
    sessions_payload,
)
from cairn.render.session_payload import session_payload


def _conn(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / ".cairn" / "ledger.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    migrate(conn)
    return conn


def _seed_run(conn: sqlite3.Connection, run_id: str = "run-1") -> None:
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, project, started_at, ended_at, status,
          total_cost, total_input_tokens, total_output_tokens, has_cost,
          event_count, waste_tokens, tool_error_count
        ) VALUES (?, 'claude-code', 'ext-1', 'proj', ?, ?, 'completed',
                  1.0, 8000, 4000, 1, 4, 500, 2)
        """,
        (run_id, now, now),
    )
    conn.execute(
        """
        INSERT INTO events (run_id, seq, type, role, text_inline, tool_name, tool_norm_name)
        VALUES (?, 1, 'user_prompt', 'user', 'hello', NULL, NULL)
        """,
        (run_id,),
    )
    conn.commit()


def test_overview_payload_shape(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    out = overview_payload(conn, days=30, repo_name="my-repo")
    assert "summary" in out
    assert out["summary"]["sessions"] == 1
    assert out["summary"]["total_cost"] == 1.0
    assert out["project_name"] == "my-repo"
    assert "data_notes" in out
    conn.close()


def test_overview_payload_includes_narrative(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    out = overview_payload(conn, days=30, repo_name="my-repo")
    narrative = out.get("narrative")
    assert narrative is not None
    assert narrative.get("headline")
    assert "cta" in narrative
    assert "cta_href" in narrative
    assert isinstance(narrative.get("sentences"), list)
    assert "diagnostics_summary" in out
    conn.close()


def test_overview_payload_narrative_with_low_waste_pct(tmp_path: Path) -> None:
    """waste_display becomes '<0.01' for tiny waste — narrative must not crash."""
    conn = _conn(tmp_path)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, project, started_at, ended_at, status,
          total_cost, total_input_tokens, total_output_tokens, has_cost,
          event_count, waste_tokens, tool_error_count
        ) VALUES ('big-run', 'claude-code', 'ext-big', 'proj', ?, ?, 'completed',
                  10.0, 5000000, 5000000, 1, 2, 100, 0)
        """,
        (now, now),
    )
    conn.commit()
    out = overview_payload(conn, days=30)
    assert out["summary"]["waste_pct"] == "<0.01"
    assert out["narrative"]["headline"]
    assert "<0.01" in out["narrative"]["headline"]
    conn.close()


def test_overview_payload_confidence_fields(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    conn.execute(
        """
        INSERT INTO data_quality (
          run_id, pct_tokens_measured, pct_tokens_estimated,
          timestamps_present, cost_source, notes_json
        ) VALUES ('run-1', 60.0, 40.0, 1, 'observed',
                  '["input estimated via heuristic (±8%)"]')
        """
    )
    conn.commit()
    out = overview_payload(conn, days=30)
    conf = out.get("confidence")
    assert conf is not None
    assert conf.get("estimation_method") != "exact"
    assert conf.get("estimation_error_pct") is not None
    conn.close()


def _seed_diagnostics_run(conn: sqlite3.Connection, run_id: str = "diag-run") -> None:
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, project, started_at, ended_at, status,
          total_cost, total_input_tokens, total_output_tokens, has_cost,
          event_count, waste_tokens, tool_error_count
        ) VALUES (?, 'claude-code', 'ext-d', 'proj', ?, ?, 'completed',
                  2.0, 12000, 3000, 1, 6, 800, 2)
        """,
        (run_id, now, now),
    )
    events = [
        (1, "user_prompt", None, None, None),
        (2, "tool_call", "read", "a.py", None),
        (3, "tool_result", None, "a.py", 1),
        (4, "tool_call", "bash", None, 1),
        (5, "tool_call", "bash", None, 1),
        (6, "tool_call", "edit", "a.py", None),
    ]
    for seq, etype, tool, path, err in events:
        conn.execute(
            """
            INSERT INTO events (
              run_id, seq, type, role, tool_norm_name, path_rel, tool_is_error,
              input_tokens, waste_tokens
            ) VALUES (?, ?, ?, 'assistant', ?, ?, ?, 100, ?)
            """,
            (run_id, seq, etype, tool, path, err or 0, 500 if err else 0),
        )
    conn.execute(
        """
        INSERT INTO diagnostics (
          run_id, outcome_label, label_source, failure_origin_event_id,
          failure_signature, primary_category, secondary_category,
          cascade_root_event_id, cascade_blast_tokens, ideal_path_savings_tokens,
          computed_at
        ) VALUES (?, 'error_exit', 'deterministic', 3, 'error_waste_spike:1.0',
                  'tool_misuse', 'loop_stall', 3, 1200, 400, ?)
        """,
        (run_id, now),
    )
    conn.commit()


def test_session_payload_includes_diagnostics(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_diagnostics_run(conn)
    out = session_payload(conn, run_id="diag-run")
    diag = out.get("diagnostics")
    assert diag is not None
    assert diag["outcome_label"] == "error_exit"
    assert out.get("failure_origin_event_id") == 3
    assert out.get("cascade_root_event_id") == 3
    assert out.get("narrative")
    assert out.get("ideal_path") is not None
    assert out["ideal_path"]["reads_actual"] >= 0
    conn.close()


def test_session_payload_no_diagnostics_honest(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    out = session_payload(conn, run_id="run-1")
    assert out.get("diagnostics") is None
    assert out.get("narrative") is None
    assert out.get("diagnosis_available") is False
    assert out.get("event_count_for_diagnosis") == 1
    conn.close()


def test_overview_data_notes_cursor_best_of_n(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, project, started_at, status,
          total_input_tokens, total_output_tokens, total_cost, has_cost
        ) VALUES ('sub-1', 'cursor', 'ext-sub', 'proj', ?, 'best-of-n-subagent', 400, 80, 0, 0)
        """,
        (now,),
    )
    conn.commit()
    out = overview_payload(conn, days=30)
    issues = {n["issue"] for n in out["data_notes"]}
    assert "best_of_n_subcomposer" in issues
    assert not any("doesn't expose token counts" in n.get("message", "") for n in out["data_notes"])
    conn.close()


def test_sessions_payload_shape(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    out = sessions_payload(conn, days=30)
    assert len(out["sessions"]) == 1
    s = out["sessions"][0]
    assert s["run_id"] == "run-1"
    assert s["has_cost"] is True
    assert s["waste_tokens"] == 500
    conn.close()


def test_session_payload_shape(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    out = session_payload(conn, run_id="run-1")
    assert out["run"]["run_id"] == "run-1"
    assert len(out["turns"]) == 1
    assert "graph" in out
    conn.close()


def test_session_payload_agents(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    now = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO runs (
          run_id, source, external_id, project, started_at, ended_at, status,
          total_cost, total_input_tokens, total_output_tokens, has_cost, event_count
        ) VALUES ('multi', 'claude-code', 'ext-m', 'proj', ?, ?, 'completed', 2.0, 1000, 200, 1, 3)
        """,
        (now, now),
    )
    conn.executemany(
        """
        INSERT INTO events (
          run_id, seq, type, agent_id, agent_lane, input_tokens, output_tokens
        ) VALUES (?, ?, 'assistant_message', ?, ?, ?, ?)
        """,
        [
            ("multi", 1, "main-agent", "main", 100, 20),
            ("multi", 2, "sub-1", "subagent", 800, 100),
            ("multi", 3, "sub-2", "sidechain", 100, 80),
        ],
    )
    conn.commit()
    out = session_payload(conn, run_id="multi")
    agents = out.get("agents")
    assert agents is not None
    assert len(agents) >= 2
    assert sum(a["tokens"] for a in agents) == 100 + 20 + 800 + 100 + 100 + 80
    assert all(a.get("cost_method") == "apportioned" for a in agents)
    conn.close()


def test_session_payload_missing(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    assert session_payload(conn, run_id="nope") == {"error": "not_found"}
    conn.close()


def test_charts_payload_shape(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    day = datetime.now(UTC).strftime("%Y-%m-%d")
    conn.execute(
        """
        INSERT INTO rollup_daily (
          day, project, source, model, sessions, cost_total, input_tokens, output_tokens,
          has_cost_sessions
        ) VALUES (?, 'proj', 'claude-code', 'claude-sonnet', 1, 1.5, 1000, 200, 1)
        """,
        (day,),
    )
    conn.commit()
    out = charts_payload(conn, days=30)
    assert "daily_cost" in out
    assert "waste_by_category" in out
    conn.close()


def test_search_payload_like(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    _seed_run(conn)
    conn.execute(
        """
        INSERT INTO events_fts (run_id, seq, text_inline)
        VALUES ('run-1', 1, 'find the gadget widget here')
        """
    )
    conn.commit()
    out = search_payload(conn, q="gadget")
    assert len(out["results"]) == 1
    assert "gadget" in out["results"][0]["excerpt"]
    conn.close()


def test_optimize_payload_shape(tmp_path: Path) -> None:
    conn = _conn(tmp_path)
    conn.execute(
        """
        INSERT INTO optimizations (
          opt_id, created_at, target_file, block_key, kind, content,
          evidence_json, status
        ) VALUES ('o1', '2026-06-12T00:00:00Z', 'AGENTS.md', 'file_guide/x', 'file_guide',
                  '- x', '{}', 'pending')
        """
    )
    conn.commit()
    out = optimize_payload(conn)
    assert len(out["optimizations"]) == 1
    assert out["optimizations"][0]["opt_id"] == "o1"
    conn.close()
