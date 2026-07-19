-- Logical SQLite fixture captured at the 1.1.1 schema boundary (migrations 0001-0005).
-- Tests build that exact schema, load this fixed user data, and then exercise the 1.2 path.
INSERT INTO workspaces (workspace_id, root_path, name, created_at)
VALUES ('legacy-workspace', '/fixture/pre-1.2-project', 'legacy', '2026-01-01T00:00:00Z');

INSERT INTO traces (
  trace_id, workspace_id, source, external_id, started_at, ended_at, status, title,
  input_tokens, output_tokens, cost, cost_source, span_count
) VALUES (
  'legacy-trace', 'legacy-workspace', 'codex', 'legacy-external',
  '2026-01-01T00:00:00Z', '2026-01-01T00:01:00Z', 'completed', 'Legacy trace',
  100, 20, 0.01, 'priced', 1
);

INSERT INTO spans (
  span_id, trace_id, seq, kind, status, input_tokens, output_tokens, text_inline
) VALUES (
  'legacy-span', 'legacy-trace', 1, 'assistant_msg', 'ok', 100, 20,
  'preserved legacy content'
);
