# ADR 0012: Query indexes and search storage

- Status: accepted
- Date: 2026-07-18

## Context

The baseline ledger had only a general `(workspace_id, started_at)` trace index. Source, project,
actor, agent, waste, insight, experiment, and reverse-link query shapes either scanned or used
single-column indexes. Search also created `spans_fts`, but production ingest did not
transactionally maintain it; only demo data populated it. The table therefore duplicated sensitive
span text without providing a correct search contract.

Search and static export also materialized unbounded intermediate row sets despite bounded HTTP
parameters.

## Decision

Migration `0007_query_indexes_and_fts_retirement.sql` adds composite/partial indexes matching the
observed workspace analytics and trace filter shapes. Query-plan tests pin the source/time and
agent/trace plans by index name.

The migration drops `spans_fts`. Search continues against canonical trace/span columns using
parameterized, case-insensitive matching. Store-owned search queries compute the exact count but
materialize no more than the requested page. This favors correct deletion/retention/privacy
semantics over claiming an unmaintained full-text index.

Repository pagination is validated even when callers bypass FastAPI. Static payload enumeration and
the file-compatible data bootstrap use bounded row batches and atomic streaming writes.

Doctor retains `quick_check` and adds read-only `foreign_key_check`.

## Consequences

- Text search remains a bounded linear scan until a content-mode-aware transactional index can
  prove insert, update, delete, rebuild, migration, and retention parity.
- Existing `spans_fts` content is derived and is removed during migration; the standard verified
  pre-migration backup preserves the old database.
- Additional indexes consume some local disk and write work, traded for predictable interactive
  filter plans.
- No query result, user-authored trace/span row, or compatibility field is removed.
