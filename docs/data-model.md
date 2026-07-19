# Data model and migrations

Cairn stores each workspace in `<workspace>/.cairn/cairn.db` using SQLite with WAL and foreign-key
checks enabled. Numbered, append-only SQL files in `server/store/migrations/` are the only schema
version mechanism; `_migrations` records each successfully applied filename.

## Upgrade behavior

Each pending migration runs in its own `BEGIN IMMEDIATE` transaction. Its schema/data changes and
its `_migrations` row commit together. A failed or interrupted migration rolls back that migration
and is retried on the next startup. Already completed migrations are not repeated.

Before applying pending migrations to a database that already has a user-data schema, Cairn:

1. runs SQLite `PRAGMA quick_check`;
2. refuses migration if the check is not `ok`;
3. creates an SQLite-consistent backup under
   `.cairn/backups/migrations/cairn.db.pre-<version>-<timestamp>.bak`;
4. verifies the backup and keeps its Unix mode at `0600` under a `0700` directory.

Fresh empty databases do not create a redundant backup. Migration backups are never uploaded or
silently deleted. Retain one until the upgraded database and important journeys are verified; any
cleanup is an explicit user action.

## Integrity and recovery

`cairn doctor` runs read-only `PRAGMA quick_check` and `foreign_key_check` diagnostics and reports
unreadable, corrupt, or referentially inconsistent databases without overwriting them. If it fails:

1. stop Cairn and preserve the damaged database plus `-wal`/`-shm` sidecars for diagnosis;
2. copy a verified backup rather than editing it in place;
3. restore the copy to `.cairn/cairn.db` with owner-only permissions;
4. run `cairn doctor` before starting normal ingestion.

Cairn does not automatically choose or restore a backup because that could discard newer user
data. The fixed pre-1.2 fixture and migration tests cover data preservation, backup contents,
repeated startup, transaction rollback, and corrupt-database diagnostics.

## Query plans and bounds

Migration `0007_query_indexes_and_fts_retirement.sql` adds indexes for the observed interactive
query shapes:

| Query shape | Index |
|---|---|
| workspace + source + time | `idx_traces_workspace_source_started` |
| workspace + project + time | `idx_traces_workspace_project_started` |
| workspace + actor + time | `idx_traces_workspace_actor_started` |
| agent trace membership | `idx_spans_agent_trace` |
| categorized waste by trace | `idx_spans_waste_trace` |
| reverse span links | `idx_span_links_to` |
| recent insights/experiments | `idx_insights_last_seen`, `idx_experiments_created` |

`EXPLAIN QUERY PLAN` behavior tests verify the two high-frequency composite paths. Public HTTP pages
remain capped at 200 rows; repositories independently reject page sizes above 1,000 and offsets
above 1,000,000 so internal callers cannot accidentally allocate an unbounded result.

Analytics aggregate builders (tools, files, agents, context trends, usage) also refuse unbounded
`fetchall`: they sample at most 25,000 span rows / 10,000 trace rows / 5,000 handoff links
(`server/store/pagination.py`) and append a truncation note to `limitations` when the sample is
incomplete. Behavior/quality fingerprint paths keep an explicit 500-session bound and say so.

Search counts all canonical trace/span matches but materializes only the requested page. Static
export enumerates row IDs in 500-row batches and streams its aggregate JavaScript data file
atomically instead of retaining every captured payload in memory.

## Search text storage

Migration 0007 removes the old `spans_fts` table. It duplicated sensitive span text but was not
maintained by production insert, update, and delete paths, so its results and retention behavior
could not be trusted. Search currently uses parameterized case-insensitive matching on the
canonical tables with explicit query/response bounds. A future full-text index must demonstrate
transactional lifecycle, content-mode, rebuild, migration, and retention parity before adoption.

See [ADR 0012](architecture/decisions/0012-query-indexes-and-search-storage.md).

## Session corrections

Migration `0013_corrections_and_relabels.sql` stores optional persisted correction ledgers
(`session_corrections`) and local user overrides (`correction_relabels`). Classification is
computed on read from high-precision `user_msg` phrase signals; relabels override class locally and
are never used for employee ranking. Schema: `cairn.corrections.v1`.

## Local regression artifacts

Filesystem-only (not SQLite): `.cairn/regressions/<regression_id>/` holds `manifest.json`,
`regression.json`, `privacy.json`, and an empty `attachments/` directory by default. Schema
`cairn.regression.v1` captures scrubbed intent, repo start reference, expected outcome rollups,
inferred verification command names, and a privacy inventory. Setup commands stay empty on create;
Cairn never executes setup/verification commands when creating, validating, or importing. See
[regressions](regressions.md).

## Verification receipts

Migration `0012_verification_receipts.sql` stores idempotent receipt snapshots keyed by `trace_id`:

| Column | Role |
|---|---|
| `schema_version` / `builder_version` | Receipt contract identity (`cairn.receipt.v1`) |
| `status` | `verified` / `failed` / `debt` / `unverified` / `unknown` |
| `debt_score` | Sum of active transparent component weights (capped at 1.0) |
| `content_hash` | SHA-256 of the deterministic receipt body |
| `receipt_json` | Full receipt payload |

Receipts are computed on read from outcomes and spans; `cairn action verification-rebuild`
persists them when the hash changes. Claim rows are intentionally absent in v1 — absence of a
claim is not “unsupported” or “contradicted.”
