ALTER TABLE outcomes ADD COLUMN quality_components_json TEXT;
ALTER TABLE outcomes ADD COLUMN quality_weights_json TEXT;
ALTER TABLE outcomes ADD COLUMN reverted_within_window INTEGER NOT NULL DEFAULT 0;
ALTER TABLE outcomes ADD COLUMN fixup_within_window INTEGER NOT NULL DEFAULT 0;
ALTER TABLE outcomes ADD COLUMN human_label TEXT CHECK(human_label IN ('up', 'down'));
ALTER TABLE outcomes ADD COLUMN human_note TEXT;
ALTER TABLE outcomes ADD COLUMN human_labeled_at TEXT;
