CREATE TABLE adapter_parse_health (
  workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
  adapter_id TEXT NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  fully_parsed INTEGER NOT NULL DEFAULT 0,
  degraded INTEGER NOT NULL DEFAULT 0,
  skipped INTEGER NOT NULL DEFAULT 0,
  unknown_fields_json TEXT NOT NULL DEFAULT '{}',
  recent_unknown_fields_json TEXT NOT NULL DEFAULT '{}',
  last_success_at TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (workspace_id, adapter_id)
);
