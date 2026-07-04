"""Schema migration + DDL smoke tests (Part 6 — 7 tables + FTS5)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from cairn.ledger.schema import SCHEMA_VERSION, migrate

_REQUIRED_TABLES = {
    "runs",
    "events",
    "optimizations",
    "rollup_daily",
    "context_regions",
    "fingerprints",
    "fingerprint_baselines",
    "outcomes",
    "data_quality",
}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    }


def test_schema_creates_all_tables_and_fts(tmp_path: Path) -> None:
    db = tmp_path / "ledger.db"
    conn = sqlite3.connect(db)
    migrate(conn)
    tables = _tables(conn)
    assert _REQUIRED_TABLES.issubset(tables), f"missing: {_REQUIRED_TABLES - tables}"
    # FTS5 virtual table
    fts = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='events_fts'"
    ).fetchall()
    assert fts, "events_fts (FTS5) missing"
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == SCHEMA_VERSION
    conn.close()


def test_runs_columns(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "ledger.db")
    migrate(conn)
    cols = _columns(conn, "runs")
    expected = {
        "run_id",
        "source",
        "external_id",
        "project",
        "model",
        "started_at",
        "ended_at",
        "status",
        "total_input_tokens",
        "total_output_tokens",
        "output_estimated",
        "cache_read_tokens",
        "cache_creation_tokens",
        "total_cost",
        "has_cost",
        "has_timestamps",
        "context_window",
        "peak_context_pct",
        "rate_limit_used_pct",
        "rate_limit_window_min",
        "rate_limit_resets_at",
        "plan_type",
        "waste_tokens",
    }
    assert expected.issubset(cols), f"runs missing: {expected - cols}"
    # PK + UNIQUE(source, external_id)
    pk = [r for r in conn.execute("PRAGMA table_info(runs)") if r[5]]
    assert any(r[1] == "run_id" for r in pk)
    conn.close()


def test_events_columns_and_unique(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "ledger.db")
    migrate(conn)
    cols = _columns(conn, "events")
    expected = {
        "event_id",
        "run_id",
        "seq",
        "ts",
        "type",
        "role",
        "model",
        "text_hash",
        "text_inline",
        "tool_name",
        "tool_norm_name",
        "tool_is_error",
        "args_hash",
        "path_rel",
        "input_tokens",
        "output_tokens",
        "input_estimated",
        "output_estimated",
        "cache_read_tokens",
        "cache_creation_tokens",
        "context_tokens_after",
        "duration_ms",
        "waste_category",
        "waste_tokens",
        "agent_id",
        "agent_lane",
    }
    assert expected.issubset(cols), f"events missing: {expected - cols}"
    # UNIQUE(run_id, seq) enforced: inserting a duplicate must fail.
    conn.execute("INSERT INTO runs (run_id, source) VALUES ('r1', 'claude-code')")
    conn.execute("INSERT INTO events (run_id, seq, type) VALUES ('r1', 1, 'user_prompt')")
    try:
        conn.execute("INSERT INTO events (run_id, seq, type) VALUES ('r1', 1, 'user_prompt')")
        raise AssertionError("events UNIQUE(run_id, seq) not enforced")
    except sqlite3.IntegrityError:
        pass
    conn.close()


def test_pillar_tables_columns(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "ledger.db")
    migrate(conn)
    assert {"event_id", "region", "tokens", "cost", "content_hash", "still_in_window"}.issubset(
        _columns(conn, "context_regions")
    )
    assert {
        "run_id",
        "project",
        "model",
        "source",
        "vector_json",
        "read_write_ratio",
        "exploration_ratio",
        "retry_rate",
        "context_fill_traj_json",
        "tool_entropy",
        "week",
    }.issubset(_columns(conn, "fingerprints"))
    assert {"project", "model", "week", "mean_vector_json", "cov_inv_json", "n"}.issubset(
        _columns(conn, "fingerprint_baselines")
    )
    assert {
        "run_id",
        "commit_sha",
        "commit_landed",
        "files_changed_json",
        "tests_run",
        "tests_passed",
        "tests_failed",
        "build_status",
        "quality_score",
        "cost_per_success",
    }.issubset(_columns(conn, "outcomes"))
    assert {
        "run_id",
        "pct_tokens_measured",
        "pct_tokens_estimated",
        "timestamps_present",
        "cost_source",
        "parser_version",
        "dropped_events",
        "notes_json",
    }.issubset(_columns(conn, "data_quality"))
    assert {"model", "difficulty_bucket", "metric", "mean", "stdev", "n"}.issubset(
        _columns(conn, "expectation_baselines")
    )
    assert {
        "run_id",
        "outcome_label",
        "primary_category",
        "failure_origin_event_id",
    }.issubset(_columns(conn, "diagnostics"))
    assert {"difficulty", "difficulty_bucket", "difficulty_features_json"}.issubset(
        _columns(conn, "runs")
    )
    assert {"effect_estimate", "effect_ci_low", "confound_flag"}.issubset(
        _columns(conn, "optimizations")
    )
    conn.close()


def test_optimizations_uses_block_key(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "ledger.db")
    migrate(conn)
    cols = _columns(conn, "optimizations")
    assert "block_key" in cols
    assert "entry_id" not in cols
    conn.close()


def test_migrate_idempotent(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "ledger.db")
    migrate(conn)
    migrate(conn)  # second call must be a no-op
    assert _REQUIRED_TABLES.issubset(_tables(conn))
    conn.close()
