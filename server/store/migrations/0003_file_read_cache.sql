CREATE TABLE file_read_cache (
  workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
  path_rel TEXT NOT NULL,
  content_hash TEXT,
  file_mtime_ns INTEGER,
  summary TEXT,
  summary_tokens INTEGER NOT NULL DEFAULT 0,
  read_count INTEGER NOT NULL DEFAULT 0,
  last_read_at TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (workspace_id, path_rel)
);

CREATE INDEX idx_file_read_cache_hot
  ON file_read_cache(workspace_id, read_count DESC, last_read_at DESC);
