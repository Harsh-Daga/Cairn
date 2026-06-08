# Phase 0 — Vision Validation

**Date:** 2026-06-09  
**Status:** ✅ Passed  
**Charter target:** Definitive open-source inference workspace for AI agents and direct LLM/provider workflows

---

## 1. Vision statement (validated)

> **Cairn = GitHub + Notion + Build System + Agent Observability + Inference Workspace**

Every project consists of **Context**, **Workflows**, **Sessions**, **Agents**, **Providers**, **Artifacts**, and **Reports** — connected through **lineage**.

This vision is **feasible** as an evolution of the existing Cairn codebase. The current product already implements ~40% of the observability and build-system pillars locally. The expansion adds collaboration, prompt libraries, unified provider/agent surfaces, live workspace, and API/SDK layers — without discarding proven foundations (ledger, CAS, capture parsers, bundle renderer).

---

## 2. Requirement validation matrix

| # | Requirement | Current state | Gap severity | Foundation to extend |
|---|-------------|---------------|--------------|----------------------|
| 1 | Project context management | `cairn.toml`, `inputs/`, `prompts/`, git metadata | Low — needs unified context registry | `loader/`, `model/project.py` |
| 2 | Real-time collaborative workspace | Local single-user only | **High** — new subsystem | Ledger + CAS as sync substrate |
| 3 | Prompt & workflow management | Project-local Jinja2 prompts; `cairn.toml` steps | Medium — needs registry + versioning | `loader/prompts.py`, `plan/` |
| 4 | Agent integration | Claude Code, Codex, Cursor, Hermes capture | Medium — Aider/OpenHands/Goose missing | `ingest/parsers/`, `watch`, `hook` |
| 5 | Direct provider workflows | OpenAI, Anthropic, Ollama, Groq via `build` | Medium — Gemini/OpenRouter not first-class | `providers/` |
| 6 | Rich inference tracking | Ledger v3, trajectories, token/cost | Low — extend for reasoning metadata | `ledger/`, `ingest/usage.py` |
| 7 | Build artifacts | `outputs/`, CAS blobs, `runs/*.json` | Low — needs first-class artifact registry | `cache/cas.py`, `render/` |
| 8 | Shareability | Offline HTML bundles v1+v3, zip export | Low — add public/private ACLs later | `render/capture_bundle.py` |
| 9 | Explainability | Turn model, graph SVG, file-first nav | Low — extend narrative engine | `render/turns.py`, `graph_layout.py` |

**Verdict:** All nine requirements are achievable incrementally. Requirements 2 (collaboration) and 3 (prompt registry) are the largest net-new surfaces. Requirements 4–9 have substantial existing code to **KEEP** and **REFACTOR**, not replace.

---

## 3. Strategic alignment decisions

### 3.1 Preserve local-first as default

The expanded vision does **not** require abandoning local-first. Collaboration layers (Phase 14) can be optional sync/remote modes. Capture mode must remain zero-config and offline-capable.

### 3.2 Unified observability model

Agent capture and provider `build` runs already share:

- Append-only ledger (`ledger/`)
- Content-addressable storage (`cache/cas.py`)
- Trajectory model (R7 in charter)
- Bundle renderer (`render/`)

**Decision:** Extend this shared model rather than building parallel pipelines. Provider workflows and agent sessions must produce identical report shapes.

### 3.3 Two-mode product becomes three surfaces

| Surface | Entry | Artifact |
|---------|-------|----------|
| **Capture** | `cairn ingest` / `watch` | Session provenance bundle |
| **Pipeline** | `cairn build` | Build outputs + bundle |
| **Workspace** (new) | `cairn live serve` / API | Live + historical inference UI |

Workspace is additive; Capture and Pipeline remain first-class.

### 3.4 Charter rewrite scope (Phase 2)

The existing `CHARTER.md` v2.0 is capture-first and pipeline-complete for Phases 0–5.5. Phase 2 must rewrite it to cover all 22 phases with no placeholders, incorporating the nine requirements above while preserving ADR decisions in `docs/adr/`.

### 3.5 Spike retirement path

`spike/` proved content-addressed DAG caching (Phase 0 spike). Production code in `cairn/` supersedes it. **Decision:** KEEP as reference through Phase 4; DELETE in Phase 22 after migration validation.

---

## 4. Phase mapping (old → new charter)

| Old (PROGRESS.md) | New charter phase | Notes |
|-------------------|-------------------|-------|
| Phase 0 spike | Phase 0 vision validation | This document |
| Phases 1–2 build engine | Phases 3–4 domain + storage | Refactor, don't rebuild |
| Phases 3–5 capture | Phases 8, 10–13 agent + graph + viz | Extend parsers and bundles |
| Phase 5.5 report excellence | Phase 12 reporting (partial) | v3 bundle is baseline |
| Phase 6 live serve | Phases 13–14 viz + collaboration | New |
| Phase 7+ | Phases 14–22 | Diff, API, SDK, security, etc. |

---

## 5. Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Scope creep to SaaS observability | Medium | High | Charter principle: local-first default |
| Collaboration over-engineering | Medium | High | Phase 14 last; file-sync before server |
| Breaking capture parsers during refactor | Low | High | Golden fixture tests (existing) |
| Charter/implementation drift | Medium | Medium | Phase gate: docs + tests before next phase |

---

## 6. Exit criteria

| Criterion | Status |
|-----------|--------|
| Nine requirements mapped to existing code or planned phases | ✅ |
| Strategic decisions documented | ✅ |
| No blocking technical impossibilities identified | ✅ |
| Baseline tests pass (121 tests) | ✅ |
| Team can proceed to Phase 1 architecture audit | ✅ |

---

## 7. Recommendation

**Proceed to Phase 1.** The vision is validated as an incremental expansion of a working local-first provenance engine, not a greenfield rewrite. Architecture audit (next) must classify every file before implementation resumes.
