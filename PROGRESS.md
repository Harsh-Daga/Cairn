# Cairn — Build Progress

**Current phase:** Phase 0 — Spike & decide  
**Charter:** [CHARTER.md](CHARTER.md) v1.1

## Phase 0 — Spike & decide

**Goal:** De-risk the core idea — content-addressed caching over a 3-node DAG.

### Exit criteria

| Criterion | Status |
|---|---|
| Throwaway 3-node DAG (map + reduce + single) | Done |
| Content-addressed caching (§9 action keys, R1 canonical JSON) | Done |
| Real provider adapter (OpenAI-compatible HTTP) | Done |
| Mock provider for offline tests | Done |
| "Edit one input → only affected nodes re-run" | Done (test + manual) |
| Golden-hash tests for canonical serialization | Done |
| Validation gate: "whoa" on a real task | **Pending (human)** |

### Deliverables

- `spike/` — isolated throwaway implementation (not production code)
- `spike/demo/` — sample corpus (3 notes + spec + 3 prompts)
- `spike/tests/` — invalidation property tests with `MockProvider`

### Known gaps (intentional for Phase 0)

- No `cairn.toml` parser, CLI, or production package layout beyond placeholder `cairn/`
- AC is JSON file, not SQLite (Phase 1 / R2)
- Chat steps only — no agents, ledger, or provenance bundle
- Golden hashes cover canonical JSON only; full action-key vectors land in Phase 1

### ADRs

| ADR | Summary |
|-----|---------|
| [0001](docs/adr/0001-independence-from-lattice-and-stratum.md) | No integration with Lattice/Stratum; Cairn stays fundamental and separate |
| [0002](docs/adr/0002-exact-action-cache-only.md) | Action cache is exact only — no semantic/approximate hits |
| [0003](docs/adr/0003-prior-art-implementation-patterns.md) | Allowlist of patterns to reimplement natively (retry, replay, coalescing, etc.) |

### Phase log

| Date | Note |
|---|---|
| 2026-06-07 | Phase 0 spike implemented under `spike/`. Property tests prove cache hits and selective invalidation. |
| 2026-06-07 | ADRs 0001–0003: independence from Lattice/Stratum, exact cache, borrowed patterns only. |

---

## Upcoming phases (not started)

- **Phase 1** — Core build engine (`init`/`validate`/`status`/`plan`/`build`, TOML, Jinja, AC+CAS)
- **Phase 2** — Provenance & sharing (Ledger, `render`, `--zip`)
- **Phase 3** — Iteration ergonomics (`diff`, selectors, `--refresh`, `--max-cost`)
- **Phase 4** — Agent nodes & tools
- **Phase 5** — Multi-agent & interop
- **Phase 6** — Polish, docs, community
