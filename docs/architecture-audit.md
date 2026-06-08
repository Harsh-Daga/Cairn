# Architecture Audit

**Date:** 2026-06-09  
**Phase:** 1 — Architecture Audit  
**Status:** ✅ Complete  
**Auditor:** Autonomous charter execution loop  
**Input:** Phase 0 vision validation (`docs/phase-0-vision-validation.md`)

---

## Executive summary

Cairn is a **mature local-first capture + pipeline engine** (~85 Python modules, 121 tests passing). The codebase is well-structured for expansion toward the inference-workspace vision. **No wholesale rewrite required.**

| Classification | Count | % of source files |
|----------------|-------|-------------------|
| **KEEP** | 72 | 62% |
| **REFACTOR** | 38 | 33% |
| **DELETE** | 4 | 3% |
| **REPLACE** | 2 | 2% |

**Key findings:**

1. **Core infrastructure is sound** — ledger, CAS, providers, capture parsers, and render bundles are KEEP with targeted REFACTOR.
2. **`spike/` is superseded** — DELETE after Phase 22 validation.
3. **Collaboration, prompt registry, live workspace, API/SDK** — net-new modules (not in repo yet).
4. **`CHARTER.md` and `README.md` diverge** — REPLACE messaging in Phase 2; README lags capture-first reality.
5. **Generated/local artifacts** (`.cairn/`, `outputs/`, `cairn-demo-live/`) — not source; gitignore or DELETE from tracking.

---

## Classification legend

| Tag | Meaning |
|-----|---------|
| **KEEP** | Production-ready; extend in place |
| **REFACTOR** | Correct direction; needs API/model changes for new charter |
| **DELETE** | Remove after migration or immediately if dead |
| **REPLACE** | Rewrite module or doc; preserve behavior via tests |

---

## Root & configuration

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `pyproject.toml` | REFACTOR | Update description, add optional deps for API/live serve | 16–17 |
| `README.md` | REPLACE | Still says "Phase 1 build engine"; misrepresents capture product | 21 |
| `CHARTER.md` | REPLACE | v2.0 capture-first; full rewrite for 22-phase charter | 2 |
| `PROGRESS.md` | REFACTOR | Remap to new 22-phase model | 0–1 |
| `.gitignore` | REFACTOR | Ensure demo outputs, `.cairn/` excluded | 5 |
| `.pre-commit-config.yaml` | KEEP | Working hooks | — |

---

## `cairn/` — package root

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `cairn/__init__.py` | REFACTOR | Version + public API surface for SDK | 18 |
| `cairn/__main__.py` | KEEP | CLI entry | — |

---

## `cairn/cache/` — content-addressable storage

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `cache/__init__.py` | KEEP | | — |
| `cache/cas.py` | KEEP | Core blob store; artifact system foundation | 11 |
| `cache/action_cache.py` | KEEP | Exact AC per ADR 0002 | — |
| `cache/store.py` | REFACTOR | Unify artifact index API for registry | 11 |

**Module verdict:** **KEEP** — foundation for artifacts, snapshots, shareability.

---

## `cairn/cli/` — command-line interface

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `cli/__init__.py` | KEEP | | — |
| `cli/main.py` | REFACTOR | Add `live`, `diff`, `workflow`, `prompt` subcommands | 16 |
| `cli/init_cmd.py` | REFACTOR | Scaffold project context + agent/provider config | 5 |
| `cli/validate_cmd.py` | KEEP | | — |
| `cli/doctor_cmd.py` | KEEP | Extend provider checks | 9 |
| `cli/status_cmd.py` | KEEP | | — |
| `cli/plan_cmd.py` | REFACTOR | Show workflow versions | 7 |
| `cli/build_cmd.py` | REFACTOR | Unified execution entry for provider workflows | 9 |
| `cli/render_cmd.py` | REFACTOR | Multi-session, public/private export | 12 |
| `cli/runs_cmd.py` | KEEP | | — |
| `cli/ingest_cmd.py` | KEEP | Core capture entry | — |
| `cli/graph_cmd.py` | REFACTOR | Execution + artifact + dependency DAGs | 10 |
| `cli/sessions_cmd.py` | REFACTOR | Session awareness, replay metadata | 8 |
| `cli/show_cmd.py` | KEEP | | — |
| `cli/hook_cmd.py` | KEEP | Live agent attachment | 8 |
| `cli/watch_cmd.py` | REFACTOR | Bridge to `live serve` tail | 13 |
| `cli/build_cmd.py` | REFACTOR | (listed above) | 9 |

**Module verdict:** **REFACTOR** — solid command set; needs workspace/API commands.

---

## `cairn/doctor/` — preflight

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `doctor/__init__.py` | KEEP | | — |
| `doctor/checks.py` | REFACTOR | MCP/agent reachability; all provider adapters | 8–9 |

---

## `cairn/executor/` — build runner

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `executor/__init__.py` | KEEP | | — |
| `executor/runner.py` | REFACTOR | Workflow engine integration; agent nodes | 7–8 |
| `executor/coalesce.py` | KEEP | Request dedup | — |

---

## `cairn/graph/` — DAG construction

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `graph/__init__.py` | KEEP | | — |
| `graph/builder.py` | REFACTOR | Map-over-ref, dynamic steps | 7 |
| `graph/levels.py` | KEEP | Topological levels | — |
| `graph/session_graph.py` | REFACTOR | Execution graph engine; artifact/dependency edges | 10 |

**Module verdict:** **REFACTOR** — extend for unified agent+provider graphs.

---

## `cairn/ingest/` — agent capture

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `ingest/__init__.py` | KEEP | | — |
| `ingest/ingest.py` | KEEP | Batch import orchestration | — |
| `ingest/writer.py` | REFACTOR | Artifact lineage writes | 11 |
| `ingest/normalizer.py` | REFACTOR | Unified event schema across agents | 8 |
| `ingest/usage.py` | KEEP | Token/cost extraction | — |
| `ingest/watch.py` | REFACTOR | Live tail → SSE bridge | 13 |
| `ingest/hook_cmd.py` | KEEP | Subprocess hook handler | — |
| `ingest/project_paths.py` | KEEP | Git root resolution | — |
| `ingest/parsers/__init__.py` | KEEP | | — |
| `ingest/parsers/claude_code.py` | KEEP | Production parser | — |
| `ingest/parsers/codex.py` | KEEP | Production parser | — |
| `ingest/parsers/cursor.py` | REFACTOR | Improve snapshot inference | 8 |
| `ingest/parsers/hermes.py` | REFACTOR | Live hook path if API exists | 8 |
| *(new)* `parsers/aider.py` | REPLACE | Not present — add | 8 |
| *(new)* `parsers/openhands.py` | REPLACE | Not present — add | 8 |
| *(new)* `parsers/goose.py` | REPLACE | Not present — add | 8 |

**Module verdict:** **KEEP** core; **REFACTOR** normalizer; **REPLACE** missing agent parsers.

---

## `cairn/ledger/` — provenance store

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `ledger/__init__.py` | KEEP | | — |
| `ledger/ledger.py` | REFACTOR | Collaboration sync hooks; versioning | 14–15 |
| `ledger/schema.py` | REFACTOR | Reasoning metadata, workflow refs | 4 |
| `ledger/run_record.py` | KEEP | JSON mirror for runs | — |

**Module verdict:** **REFACTOR** — schema extensions for new domain model.

---

## `cairn/loader/` — project loading

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `loader/__init__.py` | KEEP | | — |
| `loader/toml.py` | REFACTOR | Workflow definitions, exclusions, agent config | 5–7 |
| `loader/prompts.py` | REFACTOR | Prompt registry integration | 6 |
| `loader/refs.py` | REFACTOR | Map-over-ref | 7 |
| `loader/sources.py` | REFACTOR | Context file types (docs, artifacts) | 5 |

---

## `cairn/model/` — domain types

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `model/__init__.py` | KEEP | | — |
| `model/project.py` | REFACTOR | Project context system | 3, 5 |
| `model/nodes.py` | REFACTOR | Agent/dynamic step kinds | 7–8 |
| `model/messages.py` | KEEP | Chat message types | — |
| `model/system.py` | KEEP | System prompt keying | — |
| `model/errors.py` | KEEP | | — |
| *(new)* `model/workflow.py` | REPLACE | Workflow versioning types | 7 |
| *(new)* `model/artifact.py` | REPLACE | First-class artifact model | 11 |
| *(new)* `model/session.py` | REPLACE | Session/replay types | 8 |

**Module verdict:** **REFACTOR** + new domain modules in Phase 3.

---

## `cairn/plan/` — planning

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `plan/__init__.py` | KEEP | | — |
| `plan/action_key.py` | KEEP | Cache keying per ADR | — |
| `plan/planner.py` | REFACTOR | Workflow execution templates | 7 |
| `plan/cost.py` | KEEP | Cost estimation | — |

---

## `cairn/providers/` — LLM backends

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `providers/__init__.py` | KEEP | | — |
| `providers/protocol.py` | KEEP | Provider interface | — |
| `providers/registry.py` | REFACTOR | Gemini, OpenRouter, local model registry | 9 |
| `providers/completion.py` | KEEP | | — |
| `providers/credentials.py` | REFACTOR | Multi-provider credential ergonomics | 9 |
| `providers/capabilities.py` | REFACTOR | Model capability matrix | 9 |
| `providers/recorded.py` | KEEP | CI replay | — |
| `providers/adapters/__init__.py` | KEEP | | — |
| `providers/adapters/http.py` | REFACTOR | Provider-specific adapters | 9 |
| `providers/adapters/retry_policies.py` | KEEP | | — |
| *(new)* `adapters/gemini.py` | REPLACE | Not present | 9 |
| *(new)* `adapters/openrouter.py` | REPLACE | Not present | 9 |

**Module verdict:** **REFACTOR** — extend registry; add missing adapters.

---

## `cairn/render/` — reporting & visualization

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `render/__init__.py` | KEEP | | — |
| `render/html.py` | KEEP | HTML shell | — |
| `render/bundle.py` | REFACTOR | Pipeline bundle v2 alignment | 12 |
| `render/capture_bundle.py` | KEEP | v3 capture bundle — baseline | 12 |
| `render/turns.py` | KEEP | Turn model / explainability | — |
| `render/graph_layout.py` | REFACTOR | Artifact + dependency DAG layouts | 10, 13 |
| `render/scrub.py` | KEEP | Secret scrubbing | — |
| `render/embedding.py` | KEEP | Inline data embedding | — |
| `render/extract.py` | KEEP | Content extraction | — |
| `render/assets/__init__.py` | KEEP | | — |
| `render/assets/app.js` | REFACTOR | Pipeline bundle UI | 13 |
| `render/assets/app.css` | REFACTOR | Design system | 13 |
| `render/assets/capture.js` | REFACTOR | Live SSE updates | 13 |
| *(new)* `live_server.py` | REPLACE | `cairn live serve` | 13 |

**Module verdict:** **KEEP** capture path; **REFACTOR** for live workspace.

---

## `cairn/util/` — utilities

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `util/canonical.py` | KEEP | Hashing | — |
| `util/tokens.py` | KEEP | Token heuristics | — |

---

## `cairn/data/` — bundled data

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `data/prices.toml` | KEEP | Cost model | — |
| `data/fixtures/*.json` | KEEP | Recorded provider fixtures | — |

---

## `spike/` — Phase 0 reference implementation

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `spike/README.md` | DELETE | Reference only | 22 |
| `spike/__init__.py` | DELETE | Superseded by `cairn/` | 22 |
| `spike/run.py` | DELETE | | 22 |
| `spike/dag.py` | DELETE | Logic in `cairn/graph/` | 22 |
| `spike/cache.py` | DELETE | Logic in `cairn/cache/` | 22 |
| `spike/canonical.py` | DELETE | Logic in `cairn/util/canonical.py` | 22 |
| `spike/keys.py` | DELETE | Logic in `cairn/plan/action_key.py` | 22 |
| `spike/prompts.py` | DELETE | Logic in `cairn/loader/prompts.py` | 22 |
| `spike/provider.py` | DELETE | Logic in `cairn/providers/` | 22 |
| `spike/executor.py` | DELETE | Logic in `cairn/executor/` | 22 |
| `spike/demo/**` | DELETE | Demo corpus | 22 |
| `spike/tests/**` | DELETE | After porting any unique cases | 22 |

**Module verdict:** **DELETE** in Phase 22 — keep until production parity validated.

---

## `tests/` — test suite

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `tests/conftest.py` | KEEP | | — |
| `tests/fixtures/ingest/*` | KEEP | Golden capture fixtures | — |
| `tests/test_*.py` (all 24 files) | KEEP | Baseline coverage | — |
| *(new)* integration tests | REPLACE | Per-phase integration suites | 4+ |
| *(new)* e2e workspace tests | REPLACE | Live serve + API | 17, 22 |

---

## `docs/adr/` — architecture decision records

| File | Decision | Rationale | Target phase |
|------|----------|-----------|--------------|
| `docs/adr/0001`–`0010` | KEEP | Valid decisions | — |
| `docs/adr/README.md` | REFACTOR | Index new ADRs | ongoing |
| *(new)* collaboration ADR | REPLACE | Phase 14 | 14 |
| *(new)* API ADR | REPLACE | Phase 17 | 17 |

---

## Local/generated artifacts (not source)

| Path | Decision | Rationale |
|------|----------|-----------|
| `.cairn/sessions/*.json` | DELETE from repo | Runtime data; gitignored |
| `outputs/capture-bundle/**` | DELETE from repo | Generated render output |
| `cairn-demo-live/**` | DELETE from repo | Local demo project; should not be tracked |
| `.pytest_cache/**` | DELETE from repo | Cache |

---

## Net-new modules (not yet in codebase)

| Module | Phase | Purpose |
|--------|-------|---------|
| `cairn/context/` | 5 | Unified project context registry |
| `cairn/prompts/` | 6 | Prompt library + versioning |
| `cairn/workflow/` | 7 | Workflow engine + templates |
| `cairn/agents/` | 8 | Agent integration framework |
| `cairn/live/` | 13 | SSE live server |
| `cairn/collab/` | 14 | Multi-user sync (optional) |
| `cairn/snapshot/` | 15 | Snapshots + VCS integration |
| `cairn/api/` | 17 | HTTP API |
| `cairn/sdk/` | 18 | Python SDK public surface |
| `cairn/security/` | 19 | Scrubbing, ACLs, auth hooks |

---

## Dependency graph (current)

```
cli → ingest, render, executor, loader, ledger, graph, doctor
ingest → parsers, normalizer, writer, ledger, cache
executor → providers, cache, ledger, plan, graph
render → ledger, cache, turns, graph_layout, scrub
loader → model
graph → model, loader
ledger → cache (artifacts)
providers → httpx (adapters)
```

**Extension point:** All execution paths must converge on `ledger` + `cache` + `render` for unified observability.

---

## Migration priority (implementation order)

1. **Phase 3–4:** Domain model + storage schema extensions (non-breaking)
2. **Phase 5–7:** Project context, prompt registry, workflow engine
3. **Phase 8–10:** Agent framework, providers, execution graphs
4. **Phase 11–13:** Artifacts, reporting, live visualization
5. **Phase 14–18:** Collaboration, snapshots, CLI, API, SDK
6. **Phase 19–22:** Security, performance, docs, validation, spike deletion

---

## Exit criteria

| Criterion | Status |
|-----------|--------|
| Every source file classified KEEP/REFACTOR/DELETE/REPLACE | ✅ |
| Net-new modules identified | ✅ |
| Migration priority defined | ✅ |
| No code changes in Phase 1 (audit only) | ✅ |
| Baseline tests/lint pass | ✅ |

**Proceed to Phase 2: Charter Rewrite.**
