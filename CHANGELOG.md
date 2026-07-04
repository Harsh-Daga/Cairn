# Changelog

## v0.0.1 — 2026-07-04

Initial public release.

## v3.1.0 — 2026-07-03

### Added

- **Guard hooks**: Claude Code + Codex PreToolUse contract (`continue` / `hookSpecificOutput` deny), `cairn guard install --agent {claude|codex|both}`, fail-open advisory default
- **Stop hook**: instant post-session autopsy via `cairn hook stop` → `cairn advanced post-session`
- **Subagent cost attribution**: `agent_id` / `agent_lane` on events, session payload `agents[]`, dashboard “Cost by agent” bar, `subagent_heavy` insight
- **Parser reach**: Gemini CLI, Cline/Roo/Kilo, OpenClaw ingest
- **CI annotations**: `cairn check --format github` emits `::error` / `::warning` workflow commands

## v3.0.0 — 2026-06-28

Full rebuild around five pillars and a UI-first golden path.

### Added

- **Five pillars**: context profiling, behavioral fingerprinting (AMDM drift), outcome-anchored quality, measured optimize loop (holdout + Thompson sampling), MCP agent self-awareness
- **Cursor fix**: `state.vscdb` as canonical source — real ISO timestamps, `tokenCount`, `costInCents`; live vscdb watcher with debounced incremental re-ingest
- **Surveyor's Field Notebook** dashboard: vanilla JS, Chart.js 4.4, D3 v7, 10 waypoint pages, SSE live refresh
- **Background mode**: bare `cairn` daemonizes; `cairn stop`; `cairn --foreground`
- **MCP auto-install** (default on): writes client config for Claude Code / Cursor / Codex on first run
- **Quality gate**: `cairn check --min-quality FLOAT` (7d mean `quality_score` from outcomes)
- **Sessions export**: per-row "Export scrubbed HTML" on dashboard Sessions page
- **Best-of-N subcomposer** handling: `has_cost=0` + `best-of-n-subagent` status to prevent double-counting
- **Context-rot alignment**: profiler warning at ≥70% fill; waste `CONTEXT_ROT` at >85%

### Changed

- Single CLI surface in `cairn/cli/main.py` (no per-command modules)
- Stdlib-first: `dataclasses`, `sqlite3`, `tomllib`, `http.server` — no pydantic/fastapi
- Ledger schema v4 with `context_regions`, `fingerprints`, `outcomes` tables

### Removed

- v2 modules: workflow, plan, executor, graph engine, providers, collab, sdk, doctor, security, etc.

## v2.x (legacy)

See git history for pre-rebuild releases.
