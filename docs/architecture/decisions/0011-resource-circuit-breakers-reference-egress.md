# ADR 0011: Resource circuit breakers, reference storage, and egress accounting

Status: accepted for 1.2.0

## Context

Watcher scans are frequent/duplicated, jobs are unbounded, raw content grows indefinitely, source
drift is invisible, and optional egress is not accounted for.

## Decision

- Collection modes are Manual, Efficient (default), and explicit Live. Backend auto-sync and
  browser live updates are separate.
- One coalesced ingest path uses a bounded executor/queue, adaptive backoff, stale-watch removal,
  dedupe, cancellation, progress, expiry, and graceful shutdown.
- Per file/span/trace/import budgets cover bytes, nesting, parse time, queue/write rate, WAL/disk,
  and repeated failures. Violators are quarantined without mutating source or stopping healthy
  adapters.
- Storage modes are Metrics only, Balanced, Forensic, and Reference. Reference stores cursors,
  hashes, metrics, evidence references, and selected excerpts; it detects source drift.
- Derived indexes are rebuildable/removable. Content-addressing is adopted only after measured
  benefit.
- Every Cairn-initiated network attempt records a secret-free egress entry; default flows leave
  the ledger empty.

## Consequences

Resource state distinguishes healthy, degraded, paused by policy, quarantined, unknown, and
unavailable. Dropped/skipped evidence is always visible.
