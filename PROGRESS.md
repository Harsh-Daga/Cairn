# Cairn — Build Progress

**Current phase:** Phase 1 — Core build engine  
**Charter:** [CHARTER.md](CHARTER.md) v1.2

## Phase 0 — Spike & decide ✅

**Goal:** De-risk the core idea — content-addressed caching over a 3-node DAG.

Exit criteria met (technical); human validation gate still pending.

See git history under `spike/` for deliverables.

---

## Phase 1 — Core build engine

**Goal:** Minimum tool genuinely useful to its author — production `cairn/` package.

### Exit criteria

| Criterion | Status |
|---|---|
| `cairn init` scaffolds a working project | Done |
| `cairn validate` / `doctor` / `status` / `plan` / `build` | Done |
| `cairn.toml` + Pydantic validation; Jinja prompts with YAML front matter | Done |
| Chat steps: map / reduce / single | Done |
| Domain model (`model/`), DAG builder (`graph/`), Planner (`plan/`) | Done |
| Action keys per §9/R1; ADR 0005 (prompt keying), ADR 0006 (Merkle ordering) | Done |
| SQLite Action Cache + sharded atomic CAS (R2/R14) | Done |
| Provider layer: protocol, HTTP adapters, capability registry, credentials, retries | Done |
| `RecordedProvider` with sha256-stable fixtures (not `hash()`) | Done |
| Golden-hash + property tests (R17 #1–3, #8, #9, #12); doctor tests; e2e replay | Done |
| `mypy --strict` + `ruff` clean on `cairn/` | Done |
| Level-parallel executor (`--concurrency` actually bounds overlap) | Done |
| O(N) incremental planning (one `plan_nodes` call per level) | Done |
| `system_hash` in action key (ADR 0007) | Done |
| CAS `fsync` before atomic rename (R2) | Done |
| Output paths rendered via Jinja (not `str.replace`) | Done |
| **Validation gate (human):** two weeks on real corpus | **Pending** |

### Package layout

```
cairn/
├── cli/           # init, validate, doctor, status, plan, build
├── model/         # Project, Step, Node, messages, errors
├── loader/        # cairn.toml, prompts, sources, refs
├── graph/         # DAG builder (cycles, collisions, undeclared refs)
├── plan/          # action_key, planner, cost
├── cache/         # CAS + SQLite AC
├── providers/     # capabilities, credentials, recorded, HTTP adapters
├── executor/      # async runner, coalescing, build lock
├── doctor/        # preflight checks
└── data/          # prices.toml, provider fixtures
```

### Carry-over fixes from Phase 0 review

| Issue | Resolution |
|---|---|
| `MockProvider` used salted `hash()` | `RecordedProvider` uses `sha256` fixture keys |
| Prompt hash double-counting | ADR 0005: template body only; behavior FM → resolved config |
| Input-completeness | `validate` fails on undeclared `source()`/`ref()` in templates |
| Merkle ordering undocumented | ADR 0006: sorted digests; test pinned |
| Sync provider, no retries | Async `httpx` + R18.3 retry tables + semaphore |
| Ad-hoc Ollama endpoint logic | Folded into `providers/capabilities.py` |
| `pyproject.toml` spike override | Wheel ships `cairn/` only; strict typing on `cairn/` |

### ADRs

| ADR | Summary |
|-----|---------|
| [0001](docs/adr/0001-independence-from-lattice-and-stratum.md) | No Lattice/Stratum integration |
| [0002](docs/adr/0002-exact-action-cache-only.md) | Exact AC only |
| [0003](docs/adr/0003-prior-art-implementation-patterns.md) | Borrow patterns, not products |
| [0004](docs/adr/0004-provider-and-agent-connection-ergonomics.md) | R18 is connection-only |
| [0005](docs/adr/0005-prompt-template-keying.md) | Template-body prompt hash; no double-count |
| [0006](docs/adr/0006-merkle-input-ordering.md) | Order-independent Merkle rollup |
| [0007](docs/adr/0007-system-prompt-keying.md) | `system_hash` in action key |

### Known limitations (Phase 1)

| Item | Status |
|---|---|
| `map over ref()` / `manifest()` | Deferred to Phase 3/4 — explicit `ValidationError` |

### Phase 1 hardening (pre-first-commit)

| Item | Status |
|---|---|
| Level-parallel scheduling under semaphore | Done |
| Incremental O(N) planning | Done |
| `system_hash` + golden re-pin | Done |
| CAS fsync durability | Done |
| Jinja output paths | Done |
| Token estimate consolidation (`util/tokens.py`) | Done |

### Phase log

| Date | Note |
|---|---|
| 2026-06-07 | Phase 1 core engine: CLI, TOML, DAG, planner, SQLite AC + CAS, providers, tests green. |
| 2026-06-07 | Phase 1 hardening: concurrent executor, system_hash, CAS fsync, Jinja output paths. |

---

## Upcoming phases (not started)

- **Phase 2** — Provenance & sharing (Ledger, `render`, `--zip`)
- **Phase 3** — Iteration ergonomics (`diff`, selectors, `--refresh`, `--max-cost`)
- **Phase 4** — Agent nodes & tools
- **Phase 5** — Multi-agent & interop
- **Phase 6** — Polish, docs, community
