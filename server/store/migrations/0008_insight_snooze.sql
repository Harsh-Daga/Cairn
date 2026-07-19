-- Additive snooze and recurrence fields for insight lifecycle (T04-12).
ALTER TABLE insight_states ADD COLUMN snoozed_until TEXT;
ALTER TABLE insight_states ADD COLUMN snooze_savings_baseline REAL;
ALTER TABLE insight_states ADD COLUMN see_count INTEGER NOT NULL DEFAULT 1;

CREATE INDEX idx_insight_states_snoozed_until
  ON insight_states(snoozed_until)
  WHERE snoozed_until IS NOT NULL;
