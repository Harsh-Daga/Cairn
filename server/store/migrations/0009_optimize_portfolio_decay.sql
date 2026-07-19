-- Additive optimize portfolio / decay / proposal-source fields (T04-13).
ALTER TABLE experiments ADD COLUMN proposal_source TEXT NOT NULL DEFAULT 'local';
ALTER TABLE experiments ADD COLUMN decay_state TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE experiments ADD COLUMN last_evaluated_at TEXT;
ALTER TABLE experiments ADD COLUMN plain_verdict TEXT;
ALTER TABLE experiments ADD COLUMN confound_notes_json TEXT;
ALTER TABLE experiments ADD COLUMN effect_history_json TEXT;
ALTER TABLE experiments ADD COLUMN guard_event_id TEXT;

CREATE INDEX idx_experiments_decay_state
  ON experiments(decay_state, status);
