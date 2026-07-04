"""Cairn v3 ledger DDL — 4 core tables + 3 pillar tables + FTS5 (Part 6)."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 8
FTS_AVAILABLE = True

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  external_id TEXT,
  cwd TEXT,
  project TEXT,
  model TEXT,
  git_branch TEXT,
  git_commit TEXT,
  started_at TEXT,
  ended_at TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  total_input_tokens INTEGER NOT NULL DEFAULT 0,
  total_output_tokens INTEGER NOT NULL DEFAULT 0,
  output_estimated INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens INTEGER NOT NULL DEFAULT 0,
  total_cost REAL NOT NULL DEFAULT 0.0,
  has_cost INTEGER NOT NULL DEFAULT 0,
  has_timestamps INTEGER NOT NULL DEFAULT 0,
  context_window INTEGER,
  peak_context_pct REAL,
  rate_limit_used_pct REAL,
  rate_limit_window_min INTEGER,
  rate_limit_resets_at TEXT,
  plan_type TEXT,
  event_count INTEGER NOT NULL DEFAULT 0,
  tool_call_count INTEGER NOT NULL DEFAULT 0,
  tool_error_count INTEGER NOT NULL DEFAULT 0,
  waste_tokens INTEGER NOT NULL DEFAULT 0,
  difficulty REAL,
  difficulty_bucket TEXT,
  difficulty_features_json TEXT,
  UNIQUE(source, external_id)
);

CREATE INDEX IF NOT EXISTS idx_runs_started ON runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_project ON runs(project);
CREATE INDEX IF NOT EXISTS idx_runs_source ON runs(source);

CREATE TABLE IF NOT EXISTS events (
  event_id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  seq INTEGER NOT NULL,
  ts TEXT,
  type TEXT NOT NULL,
  role TEXT,
  model TEXT,
  text_hash TEXT,
  text_inline TEXT,
  tool_name TEXT,
  tool_norm_name TEXT,
  tool_is_error INTEGER DEFAULT 0,
  args_hash TEXT,
  path_rel TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  input_estimated INTEGER NOT NULL DEFAULT 0,
  output_estimated INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER,
  cache_creation_tokens INTEGER,
  context_tokens_after INTEGER,
  duration_ms INTEGER,
  waste_category TEXT,
  waste_tokens INTEGER DEFAULT 0,
  agent_id TEXT,
  agent_lane TEXT,
  UNIQUE(run_id, seq)
);

CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, seq);
CREATE INDEX IF NOT EXISTS idx_events_tool ON events(run_id, tool_norm_name);
CREATE INDEX IF NOT EXISTS idx_events_path ON events(path_rel);
CREATE INDEX IF NOT EXISTS idx_events_waste ON events(run_id, waste_category)
  WHERE waste_category IS NOT NULL;

CREATE TABLE IF NOT EXISTS optimizations (
  opt_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  target_file TEXT NOT NULL,
  block_key TEXT NOT NULL,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  evidence_json TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  applied_at TEXT,
  baseline_metric REAL,
  baseline_sessions INTEGER,
  outcome_metric REAL,
  outcome_sessions INTEGER,
  measured_at TEXT,
  fingerprint_distance_baseline REAL,
  fingerprint_distance_outcome REAL,
  effect_estimate REAL,
  effect_ci_low REAL,
  effect_ci_high REAL,
  test_method TEXT,
  confound_flag INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rollup_daily (
  day TEXT NOT NULL,
  project TEXT NOT NULL,
  source TEXT NOT NULL,
  model TEXT NOT NULL DEFAULT '',
  sessions INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0,
  tool_errors INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  cost_total REAL NOT NULL DEFAULT 0.0,
  waste_tokens INTEGER NOT NULL DEFAULT 0,
  has_cost_sessions INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, project, source, model)
);

CREATE TABLE IF NOT EXISTS context_regions (
  event_id INTEGER NOT NULL REFERENCES events(event_id),
  region TEXT NOT NULL,
  tokens INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0.0,
  content_hash TEXT,
  first_turn INTEGER,
  last_seen_turn INTEGER,
  still_in_window INTEGER DEFAULT 0,
  PRIMARY KEY (event_id, region)
);

CREATE TABLE IF NOT EXISTS fingerprints (
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
  project TEXT,
  model TEXT,
  source TEXT,
  ts TEXT,
  vector_json TEXT NOT NULL,
  read_write_ratio REAL,
  exploration_ratio REAL,
  retry_rate REAL,
  context_fill_traj_json TEXT,
  turn_count INTEGER,
  tool_entropy REAL,
  week TEXT
);

CREATE TABLE IF NOT EXISTS fingerprint_baselines (
  project TEXT NOT NULL,
  model TEXT NOT NULL,
  week TEXT NOT NULL,
  mean_vector_json TEXT NOT NULL,
  cov_inv_json TEXT NOT NULL,
  n INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (project, model, week)
);

CREATE INDEX IF NOT EXISTS idx_fp_project_week ON fingerprints(project, week);

CREATE TABLE IF NOT EXISTS outcomes (
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
  commit_sha TEXT,
  commit_landed INTEGER DEFAULT 0,
  files_changed_json TEXT,
  tests_run INTEGER,
  tests_passed INTEGER,
  tests_failed INTEGER,
  build_status TEXT,
  quality_score REAL,
  cost_per_success REAL,
  outcome_label TEXT,
  label_source TEXT,
  captured_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_outcomes_run ON outcomes(run_id);

CREATE TABLE IF NOT EXISTS data_quality (
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
  pct_tokens_measured REAL,
  pct_tokens_estimated REAL,
  timestamps_present INTEGER NOT NULL DEFAULT 0,
  cost_source TEXT NOT NULL DEFAULT 'absent',
  parser_version TEXT,
  dropped_events INTEGER NOT NULL DEFAULT 0,
  notes_json TEXT,
  computed_at TEXT
);

CREATE TABLE IF NOT EXISTS expectation_baselines (
  model TEXT NOT NULL,
  difficulty_bucket TEXT NOT NULL,
  metric TEXT NOT NULL,
  mean REAL,
  stdev REAL,
  n INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT,
  PRIMARY KEY (model, difficulty_bucket, metric)
);

CREATE TABLE IF NOT EXISTS diagnostics (
  run_id TEXT PRIMARY KEY REFERENCES runs(run_id),
  outcome_label TEXT,
  label_source TEXT NOT NULL DEFAULT 'deterministic',
  failure_origin_event_id INTEGER,
  failure_signature TEXT,
  primary_category TEXT,
  secondary_category TEXT,
  cascade_root_event_id INTEGER,
  cascade_blast_tokens INTEGER,
  ideal_path_savings_tokens INTEGER,
  computed_at TEXT
);

CREATE TABLE IF NOT EXISTS episodes (
  episode_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES runs(run_id),
  task_signature TEXT NOT NULL,
  approach_json TEXT NOT NULL,
  outcome_label TEXT,
  captured_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_episodes_task ON episodes(task_signature);
"""

_FTS_DDL = """
CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
  run_id UNINDEXED, seq UNINDEXED, text_inline
);
"""


def _try_create_fts(conn: sqlite3.Connection) -> bool:
    global FTS_AVAILABLE
    try:
        conn.executescript(_FTS_DDL)
        return True
    except sqlite3.OperationalError:
        FTS_AVAILABLE = False
        return False


def _drop_legacy_tables(conn: sqlite3.Connection) -> None:
    """Drop everything from pre-v3 schemas so we re-ingest clean."""
    legacy = (
        "action_cache",
        "nodes",
        "tool_calls",
        "cas_refs",
        "file_artifacts",
        "context_assets",
        "artifacts",
        "workflow_runs",
        "lineage_edges",
        "prompt_registry",
        "prompt_refs",
        "event_metrics",
        "session_metrics",
        "context_regions",
        "fingerprints",
        "fingerprint_baselines",
        "outcomes",
        "data_quality",
        "expectation_baselines",
        "diagnostics",
        "episodes",
        "events_fts",
        "events",
        "runs",
        "rollup_daily",
        "optimizations",
    )
    for name in legacy:
        with conn:
            conn.execute(f"DROP TABLE IF EXISTS {name}")


def migrate(conn: sqlite3.Connection) -> None:
    """Apply v3 schema; drop legacy schema when user_version differs."""
    conn.execute("PRAGMA busy_timeout = 30000")
    cur = conn.execute("PRAGMA user_version").fetchone()
    version = int(cur[0]) if cur else 0
    if version == SCHEMA_VERSION:
        _try_create_fts(conn)
        return
    _drop_legacy_tables(conn)
    conn.executescript(_DDL)
    _try_create_fts(conn)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()
