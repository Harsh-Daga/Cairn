# Cairn — Build Progress

**Current phase:** Phase 17 — API ✅; Phase 18 next  
**Charter:** [CHARTER.md](CHARTER.md) v3.0 — inference workspace

---

## New charter phases (v3.0)

| Phase | Name | Status |
|-------|------|--------|
| 0 | Vision Validation | ✅ `docs/phase-0-vision-validation.md` |
| 1 | Architecture Audit | ✅ `docs/architecture-audit.md` |
| 2 | Charter Rewrite | ✅ CHARTER.md v3.0 + R1–R19 preserved |
| 3 | Domain Model | ✅ `model/session.py`, `artifact.py`, `workflow.py` + tests |
| 4 | Storage Layer | ✅ ledger schema v4, `ledger/storage.py` + tests |
| 5 | Project Context System | ✅ `cairn/context/`, `cairn context` CLI + tests |
| 6 | Prompt Registry | ✅ `cairn/prompts/`, schema v5, `cairn prompt` CLI + tests |
| 7 | Workflow Engine | ✅ `cairn/workflow/`, `cairn workflow` CLI + tests |
| 8 | Agent Integration Framework | ✅ parsers, registry, replay, `cairn sessions replay` |
| 9 | Provider Framework | ✅ Gemini + OpenRouter adapters, credentials, tests |
| 10 | Execution Graph Engine | ✅ execution/artifact/dependency graphs + bundle graphs |
| 11 | Artifact System | ✅ `cairn/artifacts/`, capture sync, `cairn artifact` CLI + tests |
| 12 | Reporting Engine | ✅ `cairn/report/`, unified schema, `cairn report` CLI + tests |
| 13 | Visualization Layer | ✅ `cairn live serve`, SSE + capture.js auto-refresh + tests |
| 14 | Collaboration Layer | ✅ `cairn/collab/`, export/import sync bundles + tests |
| 15 | Snapshot & Versioning | ✅ `cairn snapshot`, `cairn diff --session`, CAS roots + tests |
| 16 | CLI | ✅ unified `cairn help` groups + e2e CLI smoke tests |
| 17 | API | ✅ `cairn api serve`, v1 routes, OpenAPI spec + tests |
| 18–22 | See CHARTER.md §20 | 🔲 Planned |

---

## Legacy phases (v2.0 — complete)

Phases 0–5.5 from the capture-first charter are **implemented**:

- Phase 0 spike (`spike/` — delete in Phase 22)
- Phase 1–2 build engine + provenance
- Phase 3–5 capture (Claude, Codex, Cursor, Hermes)
- Phase 5.5 capture report excellence (bundle v3)

180 tests passing. See git history for deliverables.

---

## Phase log

| Date | Phase | Note |
|------|-------|------|
| 2026-06-09 | 0 | Vision validated; 9 requirements mapped to codebase |
| 2026-06-09 | 1 | Architecture audit: 72 KEEP, 38 REFACTOR, 6 DELETE/REPLACE |
| 2026-06-09 | 2 | Charter v3.0: inference workspace; 22-phase plan; R1–R19 retained |
| 2026-06-09 | 3 | Domain models: Session, Artifact, WorkflowDef + 8 tests |
| 2026-06-09 | 4 | Ledger schema v4: artifacts, context_assets, workflow_runs, lineage_edges |
| 2026-06-09 | 5 | Context registry: scan/list/show, ledger-backed index |
| 2026-06-09 | 6 | Prompt registry: versioned prompts in CAS + `cairn prompt sync` |
| 2026-06-09 | 7 | Workflow engine: validate/run/history via build executor |
| 2026-06-09 | 8 | Agent framework: Aider/OpenHands/Goose parsers + session replay |
| 2026-06-09 | 9 | Provider adapters: Gemini generateContent + OpenRouter OpenAI API |
| 2026-06-09 | 10 | Graph engine: execution, artifact, dependency DAGs in bundle + CLI |
| 2026-06-09 | 11 | Artifact registry: ledger-backed inventory, lineage, capture ingest sync |
| 2026-06-09 | 12 | Unified report schema for capture + provider; `cairn report` CLI |
| 2026-06-09 | 13 | Live workspace: `cairn live serve`, session HTML, SSE event stream |
| 2026-06-09 | 14 | Collaboration sync: file-based export/import bundles + cursor |
| 2026-06-09 | 15 | Snapshots: create/list/diff/restore + session diff CLI |
| 2026-06-09 | 16 | CLI consolidation: command groups registry, help, e2e tests |
