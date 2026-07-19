-- Query-shape indexes for bounded workspace analytics and trace filtering.
CREATE INDEX idx_traces_workspace_source_started
  ON traces(workspace_id, source, started_at DESC);
CREATE INDEX idx_traces_workspace_project_started
  ON traces(workspace_id, project, started_at DESC)
  WHERE project IS NOT NULL;
CREATE INDEX idx_traces_workspace_actor_started
  ON traces(workspace_id, actor_id, started_at DESC)
  WHERE actor_id IS NOT NULL;
CREATE INDEX idx_spans_agent_trace
  ON spans(agent_id, trace_id)
  WHERE agent_id IS NOT NULL;
CREATE INDEX idx_spans_waste_trace
  ON spans(waste_category, trace_id)
  WHERE waste_category IS NOT NULL;
CREATE INDEX idx_span_links_to
  ON span_links(to_span_id, link_type);
CREATE INDEX idx_insights_last_seen
  ON insights(last_seen_at DESC);
CREATE INDEX idx_experiments_created
  ON experiments(created_at DESC);

-- The baseline FTS table was not transactionally maintained and duplicated sensitive
-- span text. Search deliberately uses the canonical spans table until a future
-- content-mode-aware index has complete insert/update/delete and retention semantics.
DROP TABLE IF EXISTS spans_fts;
