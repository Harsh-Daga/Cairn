-- Persist idempotent verification receipts (receipt v1).
CREATE TABLE IF NOT EXISTS verification_receipts (
  trace_id TEXT PRIMARY KEY REFERENCES traces(trace_id) ON DELETE CASCADE,
  schema_version TEXT NOT NULL,
  builder_version TEXT NOT NULL,
  status TEXT NOT NULL,
  debt_score REAL NOT NULL DEFAULT 0,
  content_hash TEXT NOT NULL,
  receipt_json TEXT NOT NULL,
  built_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_verification_receipts_status
  ON verification_receipts(status, built_at);
