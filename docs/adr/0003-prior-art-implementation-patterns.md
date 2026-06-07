# ADR 0003: Borrow implementation patterns, not dependencies

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** §8.3 (Protocols), §14 (pure core), §15 (RecordedProvider), R5, R12, R14, R16  
**Depends on:** [ADR 0001](0001-independence-from-lattice-and-stratum.md)

## Context

Lattice and Stratum are **discarded as products to integrate** with Cairn (ADR 0001). Both
nevertheless contain hard-won engineering patterns that align with Cairn's charter. The
question is what to **reimplement natively** inside `cairn/` without importing code or
requiring those systems at runtime.

This ADR records the allowlist of borrowed *ideas* and where they land in Cairn's module
layout (§14).

## Decision

Cairn may reimplement the following patterns **in its own codebase**, cited here as prior
art inspiration only:

### 1. Provider retry and error classification (→ `providers/`, R5)

**Inspired by:** per-provider retry rule tables and transport resilience layering.

**Cairn implementation:**

- Normative table from R5: 429 (+ `retry-after`), 529, 408/timeout, 5xx retry; 4xx fatal.
- Jittered exponential backoff; cap attempts.
- **No** automatic model/provider fallback unless explicitly configured in `cairn.toml`
  (Cairn does not route — one provider per node, analogous to Lattice's "not a router").

### 2. In-flight request coalescing (→ `execute/`, R5/R12)

**Inspired by:** coalescing concurrent identical requests by compatibility key.

**Cairn implementation:**

- Coalesce by **action key** during parallel map execution: N identical keys → one
  provider call, N waiters.
- Scoped to a single `cairn build` process; no cross-process queue.

### 3. Record / replay fixtures (→ `providers/recorded.py`, `agents/recorded.py`, §15)

**Inspired by:** trace replay benchmarks and fingerprint stability tests.

**Cairn implementation:**

- `RecordedProvider` / `RecordedAgent`: record mode writes fixtures; replay mode is CI
  default.
- Fixtures keyed by action key (or hash thereof), not by approximate request similarity.
- Golden-hash tests for planner inputs (R1); syrupy for CLI/bundle snapshots where useful.

### 4. CLI-agent preflight (→ `agents/cli.py`, `cli/`, R10 — Phase 4)

**Inspired by:** agent `doctor` / install detection / clear failure when binary missing.

**Cairn implementation:**

- `cairn validate` checks `backend = "cli:..."` templates: agent on PATH, required env
  vars present (names only, R3), sandbox writable.
- Fail loud before spend (§4 #8). **No** permanent mutation of user agent config (unlike
  `lace`/`init`); Cairn only subprocesses for the node duration.

### 5. Atomic CAS writes and SQLite discipline (→ `cache/`, `ledger/`, R2/R14)

**Inspired by:** filesystem atomicity patterns and structured SQLite schemas.

**Cairn implementation:**

- `tmp/` → `fsync` → `os.replace()` for CAS blobs (already in spike).
- Ledger migrations via `PRAGMA user_version`; human-readable `runs/<id>.json` mirror.
- **Not** porting Stratum's lessons/mistakes/traces schema — different domain.

### 6. Attribution-style lineage display (→ `render/`, R15 — Phase 2, optional depth)

**Inspired by:** packet-level influence scoring for explainability.

**Cairn implementation (limited):**

- Bundle shows **exact** lineage: source paths + hashes, prompts, model, params,
  trajectories (R15).
- Optional **heuristic** "influence" highlights in the bundle UI may be added later if they
  are clearly labeled approximate and derived from pinned blobs only — never used for cache
  lookup.
- **Not** porting Stratum's CAGE scorer or context-packet store into core.

### 7. Prefix-stable prompt shaping (→ `providers/` or executor, cost-only)

**Inspired by:** stable-prefix vs dynamic-suffix prompt splitting for provider prefix cache.

**Cairn implementation:**

- Allowed only as a **transport optimization** inside `Provider.complete()` after the
  rendered prompt is fixed.
- Must not alter action keys, ledger content, or CAS blobs (ADR 0002).

## Explicit non-borrow list

Do **not** reimplement inside Cairn core:

| Pattern | Source | Reason |
|---------|--------|--------|
| Semantic / approximate response cache | Lattice | ADR 0002 |
| 20-transform compression pipeline | Lattice | Not a build tool; changes prompt bytes unpredictably |
| Long-lived proxy server | Lattice | §4 zero-infra |
| Agent memory (lessons, mistakes, TTL traces) | Stratum | §19 agent runtime / memory |
| Embedding retrieval / sqlite-vec KNN | Stratum | §19 not a vector DB |
| Honesty calibration / abstention layer | Stratum | Eval/runtime concern, not build DAG |
| Federation / stigmergy | Stratum | Out of charter scope |

## Consequences

- Phase 1 deliverables (`providers/http`, `RecordedProvider`, retry table) have a clear
  spec without scope creep.
- Code review filter: "Is this ADR 0003 allowlist, or a sneaky integration?"
- Lattice/Stratum repos are **not modified** as part of Cairn work.

## Verification

Each borrowed pattern gets tests in Cairn only:

- Retry: unit tests with mocked HTTP status codes (R5 table).
- Coalescing: property test — concurrent duplicate keys → one provider call.
- Recorded: CI runs examples under replay (§15).
- CLI preflight: validate fails fast when `cli:` backend binary missing (R10).
