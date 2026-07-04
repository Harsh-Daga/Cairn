# Cairn v4 Completion Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every gap between current `main` and the v4 master spec (§0–11): full incremental analyzers, detector modularization, UI §7 depth, Playwright e2e, CI gates, docs, and legacy cleanup.

**Architecture:** Execute in 6 waves on branch `v4/completion-plan`, each wave ending with pytest + mypy + ruff + tsc + vitest green and a mergeable PR. Backend analyzers unblock UI data; chart kit unblocks page depth; Playwright validates acceptance flows.

**Tech Stack:** Python 3.11+ (FastAPI, SQLite, numpy), React 18 + Vite + visx + dagre + vitest + Playwright; no new runtime deps beyond spec §2.

## Global Constraints

- Dependencies: ONLY §2 lists (fastapi, pydantic, typer, numpy, httpx, tiktoken optional; react, visx, dagre, etc.)
- Port legacy logic from `cairn/` — do not rewrite fingerprint AMDM, CUPED, waste taxonomy, parsers
- Every module ≤ 400 lines; split before exceeding
- No SQL outside `server/store/`; routers call services/payloads, not raw SQL for mutations
- mypy --strict server; ruff clean; tsc --noEmit clean
- Migrations append-only; never DROP user data
- Loopback only unless `--token`
- Zero CDN URLs in scanned paths

---

## Wave 1 — Phase 4 Analyzers (P0 backend)

**Branch:** `v4/completion-plan` → PR `v4/wave-1-analyzers`

**Goal:** All incremental views registered and computing; ported tests green.

### Task 1.1: Context regions view

**Files:**
- Create: `server/store/repos/context_regions.py`
- Modify: `server/analyze/regions.py` (port `cairn/profile/decompose.py`)
- Modify: `server/analyze/registry.py`
- Test: `tests/test_analyze_regions.py`

- [ ] Port `decompose_session()` → `compute_regions(spans, trace)` using `spans_to_events()`
- [ ] Implement `RegionsView(IncrementalView)` writing `context_regions` via repo
- [ ] Map region `assistant_history` → DB `history` per §4 schema

### Task 1.2: Difficulty view

**Files:**
- Modify: `server/analyze/difficulty.py` (port `cairn/metrics/difficulty.py`)
- Test: `tests/test_analyze_difficulty.py`

- [ ] Port `estimate_difficulty()`; update `traces.difficulty` + `difficulty_bucket`

### Task 1.3: Fingerprint view + AMDM

**Files:**
- Modify: `server/analyze/fingerprint.py` (port `cairn/metrics/fingerprint.py` math verbatim)
- Modify: `server/api/payloads.py` `build_behavior()` drift series
- Test: `tests/test_analyze_fingerprint.py` (port `tests/_legacy/test_fingerprint.py`)

- [ ] `FingerprintView` upserts `fingerprints` + weekly `fingerprint_baselines`
- [ ] Expose drift points in behavior API

### Task 1.4: Diagnose view

**Files:**
- Modify: `server/analyze/diagnose.py` (port `cairn/diagnose/engine.py` + localize/cascade/ideal)
- Test: `tests/test_analyze_diagnose.py`

- [ ] `DiagnoseView` writes `diagnostics` table via `DiagnosticRepo`
- [ ] Map `failure_origin_event_id` → `failure_origin_span_id` (seq lookup)

### Task 1.5: Outcomes view

**Files:**
- Modify: `server/analyze/outcomes.py` (port `cairn/outcomes/git.py`, `tests.py`, `score.py`)
- Modify: `server/analyze/dirty.py`, `server/analyze/views.py` VIEW_ORDER
- Test: `tests/test_analyze_outcomes.py`

- [ ] `OutcomesView` captures git/test signals; writes `outcomes` via `OutcomeRepo`
- [ ] Add `outcomes` to VIEW_ORDER after `diagnose`

### Task 1.6: Registry + incremental tests

**Files:**
- Modify: `server/analyze/registry.py`
- Modify: `tests/test_analyze_incremental.py`

- [ ] Register all views in dependency order: usage → regions → waste → fingerprint → difficulty → diagnose → outcomes → rollup
- [ ] Test: 3-trace ingest → all view_state keys populated
- [ ] Test: re-sync unchanged → zero recomputes
- [ ] Test: VERSION bump → only bumped view recomputes

**DoD:** `uv run pytest -q tests/test_analyze*.py`; mypy; ruff

---

## Wave 2 — Detectors + Reflector (P0 backend)

**Branch:** `v4/wave-2-detectors`

### Task 2.1: Split detectors into §5.4 modules

**Files:**
- Create: `server/improve/detectors/{context_pressure,identical_calls,reread_hotspot,...}.py` (15 modules)
- Modify: `server/improve/engine.py`
- Test: extend `tests/test_insights.py`

- [ ] One module per detector; thresholds from `analyze/constants.py`
- [ ] Each returns `InsightDraft` with evidence refs

### Task 2.2: Reflector

**Files:**
- Modify: `server/improve/reflector.py`, `server/improve/reflector_prompt.md`
- Test: `tests/test_reflector.py`

- [ ] Evidence pack per §5.7; reject unknown evidence refs
- [ ] Backends: anthropic/openai/ollama/deterministic fallback

### Task 2.3: Port remaining ingest tests

**Files:**
- Create: `tests/test_ingest_cursor.py`, `tests/test_ingest_cline.py`, etc.
- Fixtures: all 12 under `tests/fixtures/ingest/`

- [ ] Every fixture has active (non-legacy) test
- [ ] Determinism test: parse twice → identical span_ids

**DoD:** pytest 90+; parity test green

---

## Wave 3 — UI Chart Kit + Shell (P0 frontend)

**Branch:** `v4/wave-3-ui-charts-shell`

### Task 3.1: Chart components (visx)

**Files:**
- Create: `ui/src/components/charts/Sparkline.tsx`, `StackedArea.tsx`, `HorizontalBars.tsx`, `Radar.tsx`, `ControlChart.tsx`, `IntervalPlot.tsx`, `Gauge.tsx`
- Modify: `ui/package.json` (ensure visx imports used)

### Task 3.2: Shell depth

**Files:**
- Modify: `WaypointRail.tsx` — wire Insights badge, Optimize/Live dots, plan-window gauge
- Modify: `PlaqueTopbar.tsx` — workspace meta from API, Sync action, SSE pulse
- Modify: `CommandPalette.tsx` — Pages/Sessions/Insights sections, param forms
- Modify: `Toast.tsx` — spec styling
- Modify: `server/api/payloads.py` — workspace gauge field if needed

### Task 3.3: CI vitest

**Files:**
- Modify: `.github/workflows/ci.yml` — add `npm run test` in ui job

**DoD:** tsc + vitest green in CI

---

## Wave 4 — UI Page Depth (P1 frontend)

**Branch:** `v4/wave-4-ui-pages`

### Task 4.1: Overview §7.3
- 5 KPIs, sparklines, cost stacked area, waste bars, attention list, tail curve

### Task 4.2: SessionDetail §7.4 (flagship)
- visx context timeline, blame toggle, subagent folds, inspector tabs, scrubber play

### Task 4.3: Context §7.5
- stacked composition, re-billing ledger, hotspot table

### Task 4.4: Agents §7.6
- dagre handoff DAG, actor cards, delegation economics

### Task 4.5: Behavior §7.7
- control chart, radar, EWMA sparklines

### Task 4.6: Quality §7.8
- strata funnel, histogram, cost-per-success + experiment flags, CI gate card

### Task 4.7: Optimize §7.10
- loop header, diff preview, measuring gates, verdict whiskers, reflector strip

### Task 4.8: Live, Search, Settings, Sessions, Insights depth

**DoD:** tsc + vitest; manual smoke on :8787

---

## Wave 5 — E2E + Quality Gates (P0)

**Branch:** `v4/wave-5-e2e`

### Task 5.1: Playwright setup
- Add `@playwright/test` dev dep
- `ui/playwright.config.ts`
- 3 smoke tests: Overview→Sessions→replay; insight ack+undo; live SSE event

### Task 5.2: Perf + bundle budgets
- `tests/test_waterfall_perf.py` — 10k-span render < 500ms (virtualization)
- CI check: initial JS ≤ 350KB gz

### Task 5.3: OpenAPI types generation
- Restore `scripts/build_ui.py` generate_types from `/api/openapi.json`

**DoD:** full §9 checklist green

---

## Wave 6 — Docs + Cleanup (P2)

**Branch:** `v4/wave-6-docs`

### Task 6.1: Docs rewrite
- `docs/getting-started.md`, `concepts.md`, `adapters.md`, `api.md`, `ui-tour.md`, `optimize.md`
- Fix all `ledger.db` → `cairn.db`

### Task 6.2: Legacy cleanup
- Archive or remove `cairn/` v3 tree (CDN assets)
- Update CDN grep if needed

### Task 6.3: CHANGELOG v0.1.0 final

**DoD:** full CI green; acceptance narrative checklist

---

## Execution Order & PRs

| Wave | PR | Depends on | Est. tests |
|------|-----|------------|------------|
| 1 Analyzers | #12 | — | +15 |
| 2 Detectors | #13 | 1 | +10 |
| 3 Charts+Shell | #14 | 1 | +8 vitest |
| 4 Pages | #15 | 3 | visual |
| 5 E2E | #16 | 4 | +3 playwright |
| 6 Docs | #17 | 5 | — |

## Acceptance Checklist (§11)

- [ ] `pip install cairn-workspace && cairn` opens dashboard with real narrative
- [ ] Waterfall shows subagent swimlane + replay scrubber
- [ ] Insight evidence → spans in 2 clicks
- [ ] Optimize apply → measure → verdict with n_effective
- [ ] Second actor chip without config
- [ ] Every UI action exists as CLI command
- [ ] Zero external network requests
