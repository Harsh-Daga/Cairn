-- Guard instruction-file edit events (T04-16 / ADR-0007).
CREATE TABLE IF NOT EXISTS guard_events (
  event_id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  path_rel TEXT NOT NULL,
  event_kind TEXT NOT NULL,
  commit_sha TEXT,
  parent_sha TEXT,
  before_hash TEXT,
  after_hash TEXT,
  diff_summary TEXT,
  git_state TEXT NOT NULL,
  source TEXT NOT NULL DEFAULT 'git',
  confound_notes_json TEXT,
  linked_experiment_id TEXT,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_guard_events_workspace_time
  ON guard_events(workspace_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_guard_events_path
  ON guard_events(workspace_id, path_rel, occurred_at DESC);
