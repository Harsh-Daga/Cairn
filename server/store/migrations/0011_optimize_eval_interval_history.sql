-- Opportunistic portfolio re-evaluation metadata (T05-04).
ALTER TABLE experiments ADD COLUMN eval_interval_days INTEGER NOT NULL DEFAULT 30;
ALTER TABLE experiments ADD COLUMN verdict_history_json TEXT;
ALTER TABLE experiments ADD COLUMN regression_outside_interval INTEGER NOT NULL DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_experiments_last_evaluated
  ON experiments(last_evaluated_at);
