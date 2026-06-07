# ADR 0002: Action cache is exact content-addressed only

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** §2 (core idea), §9 (cache-key algorithm), §12.5 (side-effect safety), R1, R17 #1–#3

## Context

Prior art (e.g. Lattice Semantic Cache) uses **two layers**:

1. **Exact match** — SHA-256 of canonical request JSON.
2. **Approximate match** — semantic fingerprint / Jaccard similarity above a threshold
   (e.g. 0.86) to return a "close enough" cached response.

Approximate caching improves hit rate for *chatty, repetitive* single-request workloads.
It is a good fit for a **transport proxy**.

Cairn's core move (§2) is different: impose **pseudo-hermeticity** on build nodes by
pinning the **realized output** keyed by a precise **action key**. Downstream nodes
consume **content hashes** in a Merkle rollup (§9). If the action cache returned a
near-miss blob:

- Downstream keys would not match the true input lineage.
- Reproducibility guarantees (R17 #1, #3) would break silently.
- `cairn diff` and the provenance bundle would lie about what produced an output.
- Effectful agent replay (§12.5) would become even less safe.

## Decision

1. The **Action Cache (AC)** maps `action_key → output_hash` with **exact key equality
   only**. No fuzzy, semantic, TTL-expiry, or "similar request" hits.
2. A cache hit returns the CAS blob at `output_hash`. Miss → run node → pin result.
3. **Invalidation** is driven solely by action-key change (input/prompt/model/params/tools/
   budget/sample_index per §9) or explicit user action (`--refresh`, `volatile`
   materialization).
4. **No TTL sweep** on AC entries for correctness; GC (R2) reclaims unreferenced CAS blobs
   only, not "stale but still valid" keys.
5. Provider-side **prefix caching** or transport optimizations may exist inside the
   Provider adapter but **must not** change action keys, stored outputs, or ledger
   records.

## Consequences

**Positive**

- Aligns with Bazel/dbt mental model: same inputs → same artifact bytes.
- Property tests are crisp: "build twice, zero tokens" (R17 #1); "one map input edited →
  exactly one child stale" (R17 #2).
- Provenance bundle lineage is hash-grounded (R15).

**Negative**

- Lower hit rate than approximate caching when users tweak prompts slightly without
  changing declared inputs — **by design**; they must use `--refresh` or accept a new key
  when inputs to the key change.
- Paraphrased duplicate map items with different file bytes remain distinct keys (correct
  for content-addressing).

## What we explicitly do not port

From Lattice-style semantic cache:

- Jaccard / embedding similarity for AC lookup
- `x-lattice-disable-cache` per-request bypass (Cairn uses `--refresh` + selectors, R13)
- Redis-backed shared AC (Cairn AC is local SQLite per R2; zero-infra)

From Stratum-style engine cache:

- Query-hash LRU with TTL for assessments
- Confidence-weighted eviction

Those serve **session/runtime** workloads, not **build artifact** pinning.

## Implementation notes (Phase 1+)

- `plan/` classifies nodes `cached-hit` | `stale` | `new` only via exact AC lookup.
- Golden-hash tests (R1) lock action-key digests; any AC looseness fails CI.
- Spike (`spike/cache.py`) already follows exact bind; production moves AC to SQLite
  (`action_cache` table, R14) with the same semantics.
