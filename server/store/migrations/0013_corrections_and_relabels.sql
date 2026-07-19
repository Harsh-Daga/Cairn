-- Session correction classifications and local user relabels (supervision v1).
CREATE TABLE IF NOT EXISTS session_corrections (
  trace_id TEXT PRIMARY KEY REFERENCES traces(trace_id) ON DELETE CASCADE,
  schema_version TEXT NOT NULL,
  builder_version TEXT NOT NULL,
  correction_count INTEGER NOT NULL DEFAULT 0,
  unresolved_count INTEGER NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL,
  corrections_json TEXT NOT NULL,
  built_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_session_corrections_counts
  ON session_corrections(correction_count, unresolved_count);

CREATE TABLE IF NOT EXISTS correction_relabels (
  correction_id TEXT PRIMARY KEY,
  trace_id TEXT NOT NULL REFERENCES traces(trace_id) ON DELETE CASCADE,
  original_class TEXT NOT NULL,
  relabel_class TEXT NOT NULL,
  note TEXT,
  labeled_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_correction_relabels_trace
  ON correction_relabels(trace_id);
