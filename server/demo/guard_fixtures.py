"""Deterministic Guard instruction-event fixtures for demo workspaces."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from server.demo.scenarios import DEMO_WORKSPACE_ID


def seed_guard_fixtures(conn: sqlite3.Connection, *, now: datetime) -> None:
    occurred = (now - timedelta(days=3)).isoformat()
    created = now.isoformat()
    event_id = "demo-guard-event-001"
    conn.execute(
        """
        INSERT OR REPLACE INTO guard_events (
          event_id, workspace_id, occurred_at, path_rel, event_kind, commit_sha,
          parent_sha, before_hash, after_hash, diff_summary, git_state, source,
          confound_notes_json, linked_experiment_id, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            DEMO_WORKSPACE_ID,
            occurred,
            "AGENTS.md",
            "edit",
            "abcd1234abcd1234abcd1234abcd1234abcd1234",
            "bbbb2222bbbb2222bbbb2222bbbb2222bbbb2222",
            "hash-before",
            "hash-after",
            "AGENTS.md | 1 file changed, 2 insertions(+)",
            "clean",
            "git",
            '["Demo fixture; association language stays non-causal."]',
            "demo-exp-verdict-001",
            created,
        ),
    )
    conn.execute(
        "UPDATE experiments SET guard_event_id = ? WHERE experiment_id = ?",
        (event_id, "demo-exp-verdict-001"),
    )
