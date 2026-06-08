"""R14 ledger DDL and PRAGMA user_version migrations (non-destructive)."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 4

_ACTION_CACHE_V1 = """
CREATE TABLE IF NOT EXISTS action_cache (
  action_key TEXT PRIMARY KEY,
  output_hash TEXT NOT NULL,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT NOT NULL,
  model TEXT
);
"""

_LEDGER_TABLES_V2 = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  total_cost REAL,
  total_input_tokens INTEGER,
  total_output_tokens INTEGER,
  cairn_version TEXT,
  key_version INTEGER,
  git_commit TEXT
);

CREATE TABLE IF NOT EXISTS nodes (
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  step TEXT NOT NULL,
  item_id TEXT,
  kind TEXT NOT NULL,
  action_key TEXT NOT NULL,
  output_hash TEXT,
  status TEXT NOT NULL,
  model TEXT NOT NULL,
  params_json TEXT NOT NULL,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cost REAL,
  duration_ms INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL,
  rendered_prompt TEXT,
  system_prompt TEXT,
  PRIMARY KEY (run_id, node_id)
);

CREATE TABLE IF NOT EXISTS tool_calls (
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  tool_id TEXT,
  name TEXT,
  args_hash TEXT,
  result_hash TEXT,
  is_error INTEGER,
  duration_ms INTEGER,
  PRIMARY KEY (run_id, node_id, seq)
);

CREATE TABLE IF NOT EXISTS cas_refs (
  output_hash TEXT NOT NULL,
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  PRIMARY KEY (output_hash, run_id, node_id)
);
"""

_CAPTURE_TABLES_V3 = """
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE IF NOT EXISTS file_artifacts (
  run_id TEXT NOT NULL,
  path_rel TEXT NOT NULL,
  first_seq INTEGER NOT NULL,
  last_seq INTEGER NOT NULL,
  before_hash TEXT,
  after_hash TEXT,
  PRIMARY KEY (run_id, path_rel, last_seq)
);
"""

_V3_RUNS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("kind", "TEXT NOT NULL DEFAULT 'build'"),
    ("source", "TEXT"),
    ("external_id", "TEXT"),
    ("cwd", "TEXT"),
    ("git_branch", "TEXT"),
    ("trajectory_hash", "TEXT"),
)

_V3_UNIQUE_SOURCE_EXTERNAL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_runs_source_external_id
ON runs(source, external_id)
WHERE source IS NOT NULL AND external_id IS NOT NULL;
"""

_V4_RUNS_COLUMNS: tuple[tuple[str, str], ...] = (
    ("workflow_ref", "TEXT"),
    ("context_digest", "TEXT"),
)

_V4_TABLES = """
CREATE TABLE IF NOT EXISTS context_assets (
  path_rel TEXT PRIMARY KEY,
  content_hash TEXT NOT NULL,
  mime TEXT,
  git_blob TEXT,
  tags_json TEXT NOT NULL DEFAULT '[]',
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artifacts (
  content_hash TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  path_rel TEXT,
  mime TEXT,
  run_id TEXT,
  session_id TEXT,
  size_bytes INTEGER,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_run_id ON artifacts(run_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_session_id ON artifacts(session_id);

CREATE TABLE IF NOT EXISTS workflow_runs (
  run_id TEXT PRIMARY KEY,
  workflow_ref TEXT NOT NULL,
  context_digest TEXT NOT NULL,
  git_commit TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lineage_edges (
  edge_id INTEGER PRIMARY KEY AUTOINCREMENT,
  relation TEXT NOT NULL,
  from_id TEXT NOT NULL,
  to_id TEXT NOT NULL,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  run_id TEXT
);

CREATE INDEX IF NOT EXISTS idx_lineage_from ON lineage_edges(from_id);
CREATE INDEX IF NOT EXISTS idx_lineage_to ON lineage_edges(to_id);
CREATE INDEX IF NOT EXISTS idx_lineage_run ON lineage_edges(run_id);
"""


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    existing = _table_columns(conn, "runs")
    for col, decl in _V3_RUNS_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {decl}")
    conn.execute("UPDATE runs SET kind = 'build' WHERE kind IS NULL OR kind = ''")
    conn.executescript(_CAPTURE_TABLES_V3)
    conn.executescript(_V3_UNIQUE_SOURCE_EXTERNAL)
    conn.execute("PRAGMA user_version = 3")
    conn.commit()


def _migrate_v3_to_v4(conn: sqlite3.Connection) -> None:
    existing = _table_columns(conn, "runs")
    for col, decl in _V4_RUNS_COLUMNS:
        if col not in existing:
            conn.execute(f"ALTER TABLE runs ADD COLUMN {col} {decl}")
    conn.executescript(_V4_TABLES)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def migrate(conn: sqlite3.Connection) -> None:
    """Apply pending migrations. Never drops existing tables or data."""
    version = _current_version(conn)
    if version == 0:
        conn.executescript(_ACTION_CACHE_V1)
        conn.executescript(_LEDGER_TABLES_V2)
        _migrate_v2_to_v3(conn)
        version = _current_version(conn)
    if version == 1:
        conn.executescript(_LEDGER_TABLES_V2)
        _migrate_v2_to_v3(conn)
        version = _current_version(conn)
    if version == 2:
        _migrate_v2_to_v3(conn)
        version = _current_version(conn)
    if version == 3:
        _migrate_v3_to_v4(conn)
        return
    if version != SCHEMA_VERSION:
        msg = f"unsupported ledger schema version {version} (expected {SCHEMA_VERSION})"
        raise RuntimeError(msg)
