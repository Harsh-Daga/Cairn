# ADR 0008: Ledger is append-only provenance, never an input to caching

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** R14, R18, ADR 0002, Phase 2 §3

## Context

Phase 2 promotes `.cairn/ledger.db` from Action Cache (AC) storage to a full run ledger:
`runs`, `nodes`, `tool_calls`, `cas_refs`, plus the existing `action_cache` table. The ledger
records what happened on every build — prompts, models, tokens, costs, and CAS roots.

A richer store increases the temptation to reuse provenance data for cache decisions (e.g.
“skip this node because the ledger says it ran yesterday with the same key”). That would
violate the pseudo-hermetic build model (§2, ADR 0002).

## Decision

1. The ledger is **append-only provenance**. It records build history; it is never read during
   `plan`, action-key computation, or cache lookup.
2. **Action keys and plan classification** depend only on the project graph, resolved inputs, and
   the AC view (`action_key → output_hash` + CAS blob presence).
3. `cas_refs` links outputs to runs for future GC (Phase 3); it does not affect cache hits.
4. Property tests assert that populating the ledger does not change action keys or plan
   classification when the cache view is held constant.

## Consequences

- Executor writes run/node/cas_ref rows after cache decisions are already made.
- `cairn render` and `runs/<id>.json` consume ledger data offline; the build path does not.
- Phase 4 agent `tool_calls` rows follow the same boundary: written for audit, not for replay
  keying (effectful agents remain uncached per §12.5).
