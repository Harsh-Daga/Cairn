"""R14 ledger DDL and PRAGMA user_version migrations (non-destructive)."""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2

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


def _current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0


def migrate(conn: sqlite3.Connection) -> None:
    """Apply pending migrations. Never drops existing tables or data."""
    version = _current_version(conn)
    if version == 0:
        conn.executescript(_ACTION_CACHE_V1)
        conn.executescript(_LEDGER_TABLES_V2)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        return
    if version == 1:
        conn.executescript(_LEDGER_TABLES_V2)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
        return
    if version != SCHEMA_VERSION:
        msg = f"unsupported ledger schema version {version} (expected {SCHEMA_VERSION})"
        raise RuntimeError(msg)
