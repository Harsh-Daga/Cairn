CREATE TABLE workspaces (
  workspace_id TEXT PRIMARY KEY,          -- ULID
  root_path TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE actors (                      -- multi-user support
  actor_id TEXT PRIMARY KEY,               -- ULID
  kind TEXT NOT NULL CHECK(kind IN ('human','agent','service')),
  display_name TEXT NOT NULL,
  identity_hint TEXT,                      -- git email / os user / hostname
  UNIQUE(kind, identity_hint)
);

CREATE TABLE traces (
  trace_id TEXT PRIMARY KEY,               -- ULID (adapter-derived, stable)
  workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id),
  source TEXT NOT NULL,                    -- adapter id: claude_code|codex|cursor|...
  external_id TEXT,                        -- source-native session id
  actor_id TEXT REFERENCES actors(actor_id),
  project TEXT, cwd TEXT, model TEXT,
  git_branch TEXT, git_commit TEXT,
  started_at TEXT, ended_at TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  title TEXT,                              -- first user message, truncated 120 chars
  -- denormalized rollups (maintained by analyze/usage.py, provenance-tracked):
  input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0,
  cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  reasoning_tokens INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0, cost_source TEXT NOT NULL DEFAULT 'absent',
  context_window INTEGER, peak_context_pct REAL,
  span_count INTEGER NOT NULL DEFAULT 0,
  tool_calls INTEGER NOT NULL DEFAULT 0, tool_errors INTEGER NOT NULL DEFAULT 0,
  waste_tokens INTEGER NOT NULL DEFAULT 0,
  difficulty REAL, difficulty_bucket TEXT,
  UNIQUE(source, external_id)
);
CREATE INDEX idx_traces_started ON traces(workspace_id, started_at DESC);
CREATE INDEX idx_traces_project ON traces(project);

CREATE TABLE spans (
  span_id TEXT PRIMARY KEY,                -- ULID
  trace_id TEXT NOT NULL REFERENCES traces(trace_id),
  parent_span_id TEXT REFERENCES spans(span_id),   -- NULL = root; THE causality edge
  seq INTEGER NOT NULL,                    -- stable order within trace
  kind TEXT NOT NULL CHECK(kind IN
    ('agent','llm_call','tool_call','tool_result','user_msg','assistant_msg',
     'retrieval','subagent','compaction','system')),
  name TEXT,                               -- tool name / model / agent name
  agent_id TEXT, agent_lane TEXT,          -- kept for source fidelity
  started_at TEXT, ended_at TEXT, duration_ms INTEGER,
  status TEXT NOT NULL DEFAULT 'ok' CHECK(status IN ('ok','error','cancelled')),
  model TEXT,
  input_tokens INTEGER, output_tokens INTEGER,
  input_estimated INTEGER NOT NULL DEFAULT 0, output_estimated INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER, cache_creation_tokens INTEGER,
  context_tokens_after INTEGER,
  text_inline TEXT, text_hash TEXT, args_hash TEXT, path_rel TEXT,
  waste_category TEXT, waste_tokens INTEGER NOT NULL DEFAULT 0,
  attrs_json TEXT,                         -- OTel-style attribute bag (gen_ai.* keys)
  UNIQUE(trace_id, seq)
);
CREATE INDEX idx_spans_trace ON spans(trace_id, seq);
CREATE INDEX idx_spans_parent ON spans(parent_span_id);
CREATE INDEX idx_spans_tool ON spans(trace_id, kind, name);
CREATE INDEX idx_spans_path ON spans(path_rel) WHERE path_rel IS NOT NULL;

CREATE TABLE span_links (                  -- non-tree causality (handoffs, shared artifacts)
  from_span_id TEXT NOT NULL REFERENCES spans(span_id),
  to_span_id TEXT NOT NULL REFERENCES spans(span_id),
  link_type TEXT NOT NULL CHECK(link_type IN ('handoff','retry_of','caused_by','reads_output_of')),
  PRIMARY KEY (from_span_id, to_span_id, link_type)
);

CREATE TABLE context_regions (             -- ported; keyed to spans
  span_id TEXT NOT NULL REFERENCES spans(span_id),
  region TEXT NOT NULL,                    -- system|tool_schema|tool_result|retrieved|user|history
  tokens INTEGER NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0,
  content_hash TEXT, first_turn INTEGER, last_seen_turn INTEGER,
  still_in_window INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (span_id, region)
);

CREATE TABLE fingerprints (
  trace_id TEXT PRIMARY KEY REFERENCES traces(trace_id),
  project TEXT, model TEXT, source TEXT, week TEXT, ts TEXT,
  vector_json TEXT NOT NULL,
  read_write_ratio REAL, exploration_ratio REAL, retry_rate REAL,
  tool_entropy REAL, turn_count INTEGER, context_fill_traj_json TEXT
);
CREATE TABLE fingerprint_baselines (
  project TEXT NOT NULL, model TEXT NOT NULL, week TEXT NOT NULL,
  mean_vector_json TEXT NOT NULL, cov_inv_json TEXT NOT NULL, n INTEGER NOT NULL,
  PRIMARY KEY (project, model, week)
);

CREATE TABLE outcomes (
  trace_id TEXT PRIMARY KEY REFERENCES traces(trace_id),
  commit_sha TEXT, commit_landed INTEGER DEFAULT 0, files_changed_json TEXT,
  tests_run INTEGER, tests_passed INTEGER, tests_failed INTEGER, build_status TEXT,
  quality_score REAL, cost_per_success REAL,
  outcome_label TEXT, label_source TEXT, captured_at TEXT
);

CREATE TABLE diagnostics (                 -- ported failure localization
  trace_id TEXT PRIMARY KEY REFERENCES traces(trace_id),
  failure_origin_span_id TEXT, failure_signature TEXT,
  primary_category TEXT, secondary_category TEXT,
  cascade_root_span_id TEXT, cascade_blast_tokens INTEGER,
  ideal_path_savings_tokens INTEGER, computed_at TEXT
);

-- ===== PROVENANCE + INCREMENTAL VIEWS (new, load-bearing) =====
CREATE TABLE evidence (
  evidence_id TEXT PRIMARY KEY,            -- ULID
  producer TEXT NOT NULL,                  -- e.g. 'detector:reread-hotspot@2'
  produced_at TEXT NOT NULL,
  trace_ids_json TEXT NOT NULL,            -- contributing traces
  span_ids_json TEXT,                      -- contributing spans (optional)
  metrics_json TEXT NOT NULL               -- the numbers used, snapshotted
);

CREATE TABLE view_state (                  -- incremental view maintenance ledger
  view TEXT NOT NULL,                      -- 'usage','regions','waste','fingerprint',...
  key TEXT NOT NULL,                       -- usually trace_id or (day,project) composite
  version INTEGER NOT NULL,                -- analyzer code version; bump => dirty
  input_hash TEXT NOT NULL,                -- hash of source rows consumed
  computed_at TEXT NOT NULL,
  PRIMARY KEY (view, key)
);

CREATE TABLE rollup_daily (                -- ported; now maintained incrementally
  day TEXT NOT NULL, workspace_id TEXT NOT NULL, project TEXT NOT NULL,
  source TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
  traces INTEGER NOT NULL DEFAULT 0, tool_calls INTEGER NOT NULL DEFAULT 0,
  tool_errors INTEGER NOT NULL DEFAULT 0,
  input_tokens INTEGER NOT NULL DEFAULT 0, output_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0, cache_creation_tokens INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0, waste_tokens INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (day, workspace_id, project, source, model)
);

-- ===== INSIGHTS with lifecycle =====
CREATE TABLE insights (
  insight_id TEXT PRIMARY KEY,             -- ULID
  fingerprint TEXT NOT NULL UNIQUE,        -- stable dedupe key: detector+subject hash
  detector TEXT NOT NULL, detector_version INTEGER NOT NULL,
  severity TEXT NOT NULL CHECK(severity IN ('info','suggestion','warning','error')),
  title TEXT NOT NULL, body TEXT NOT NULL,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  savings_estimate REAL, savings_ci_json TEXT,
  action TEXT,                             -- action-registry name, deep-linkable
  created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL
);
CREATE TABLE insight_states (
  insight_id TEXT PRIMARY KEY REFERENCES insights(insight_id),
  state TEXT NOT NULL DEFAULT 'new' CHECK(state IN ('new','ack','fixed','regressed','muted')),
  changed_at TEXT NOT NULL, changed_by TEXT
);

-- ===== EXPERIMENTS (the measured improvement loop) =====
CREATE TABLE experiments (
  experiment_id TEXT PRIMARY KEY,          -- ULID
  created_at TEXT NOT NULL,
  target_file TEXT NOT NULL,               -- AGENTS.md | CLAUDE.md | .cursor/rules | mcp.json
  block_key TEXT NOT NULL, kind TEXT NOT NULL, content TEXT NOT NULL,
  evidence_id TEXT NOT NULL REFERENCES evidence(evidence_id),
  status TEXT NOT NULL DEFAULT 'proposed'
    CHECK(status IN ('proposed','applied','measuring','verdict','reverted','rejected')),
  applied_at TEXT, min_holdout INTEGER NOT NULL DEFAULT 8,
  baseline_metric REAL, baseline_n_effective REAL,
  outcome_metric REAL, outcome_n_effective REAL,
  effect_estimate REAL, effect_ci_low REAL, effect_ci_high REAL,
  test_method TEXT, verdict TEXT, confound_flag INTEGER NOT NULL DEFAULT 0,
  measured_at TEXT
);

CREATE TABLE annotations (                 -- human notes on traces/spans/insights
  annotation_id TEXT PRIMARY KEY, subject_type TEXT NOT NULL, subject_id TEXT NOT NULL,
  body TEXT NOT NULL, author TEXT, created_at TEXT NOT NULL
);

CREATE TABLE data_quality (                -- ported, keyed to traces
  trace_id TEXT PRIMARY KEY REFERENCES traces(trace_id),
  pct_tokens_measured REAL, pct_tokens_estimated REAL,
  timestamps_present INTEGER NOT NULL DEFAULT 0,
  cost_source TEXT NOT NULL DEFAULT 'absent', parser_version TEXT,
  dropped_events INTEGER NOT NULL DEFAULT 0, notes_json TEXT, computed_at TEXT
);

CREATE TABLE ingest_cursors (              -- per-adapter incremental position
  source TEXT NOT NULL, stream TEXT NOT NULL, cursor_json TEXT NOT NULL,
  updated_at TEXT NOT NULL, PRIMARY KEY (source, stream)
);

-- FTS (best-effort)
CREATE VIRTUAL TABLE spans_fts USING fts5(trace_id UNINDEXED, span_id UNINDEXED, text_inline);
