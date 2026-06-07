# ADR 0001: Cairn stays independent of Lattice and Stratum

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** §4 (do one thing well; compose, don't absorb), §19 (non-goals), R16 (network egress)

## Context

Prior work exists on related problems:

- **Lattice** — LLM transport and per-request efficiency (compression, semantic response
  cache, proxy, agent `lace` routing).
- **Stratum** — agent-loop context injection, honesty calibration, SQLite memory
  (lessons/traces), attribution scoring.

Both overlap *surface area* with Cairn (caching, providers, agents, SQLite, MCP) but solve
**different primary problems**. There is a recurring temptation to integrate them — route
Cairn through a Lattice proxy, embed Stratum inside agent nodes, or ship a combined
distribution.

The charter defines Cairn as a **local-first, zero-infra build system** with a single
binary and no required services. Integration would blur product boundaries, add
dependencies, and pull Cairn toward being a transport layer or agent-memory runtime —
both explicit non-goals (§19).

Lattice and Stratum are **discarded as integration targets**. Their ideas may inform Cairn
implementation; the products themselves are not combined with Cairn.

## Decision

1. **No runtime dependency** on Lattice, Stratum, or any wrapper that requires them at
   `cairn build` time.
2. **No bundled proxy, sidecar, or companion service** in the Cairn core distribution.
3. **No import of Lattice/Stratum code** into `cairn/`. Patterns may be reimplemented
   natively where the charter requires them (see ADR 0003).
4. **No documentation** presenting Cairn as "Cairn + Lattice" or "Cairn + Stratum" as the
   default or recommended install path.
5. **Composition is out of scope for v1.** Users may independently run other tools in their
   environment; Cairn does not detect, configure, or require them.
6. **Public contracts** (`cairn.toml`, action keys, CLI) remain Cairn-owned and versioned
   (Coding Rule #10). No shared config schema with other projects.

## Consequences

**Positive**

- Cairn remains **fundamental and separable**: delete Cairn, keep inputs/outputs; no
  orphaned infra (§4 principle #6).
- Clear positioning: Cairn = build + provenance over a corpus; not transport optimization
  or agent memory.
- Smaller dependency surface; `uvx cairn` / single binary stays credible (§13).

**Negative**

- Per-request compression and semantic response caching from Lattice are **not** available
  unless re-derived inside Cairn's Provider adapter (transport-only, transparent to action
  keys) — and only if charter scope allows.
- Agent-loop context learning from Stratum is **not** built into Cairn agent nodes; users
  who want that use a separate tool.

**Follow-ups**

- ADR 0002 — cache semantics (reject Lattice-style approximate cache for the action cache).
- ADR 0003 — which prior-art *patterns* Cairn reimplements on its own.

## Alternatives considered

| Alternative | Rejected because |
|-------------|------------------|
| Optional `cairn[ lattice]` extra | Still couples releases, docs, and mental model; violates "fundamental and separate." |
| Default Provider `base_url` → Lattice proxy | Requires standing up a server; breaks zero-infra default (§4 #1). |
| Stratum as built-in agent memory | Turns Cairn into an agent runtime / memory system (§19). |
| Monorepo merging all three | Scope explosion; three products, three audiences. |
