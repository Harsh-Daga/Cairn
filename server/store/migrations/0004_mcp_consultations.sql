CREATE TABLE mcp_consultations (
  event_id TEXT PRIMARY KEY,
  workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
  trace_id TEXT NOT NULL REFERENCES traces(trace_id),
  after_seq INTEGER NOT NULL,
  tool_name TEXT NOT NULL,
  called_at TEXT NOT NULL,
  imported_at TEXT NOT NULL
);

CREATE INDEX idx_mcp_consultations_trace
  ON mcp_consultations(trace_id, after_seq, called_at);
