# Changelog

## 4.0.0 (2026-07-05)

Launch release — v4 rewrite ships as the only supported tree.

### Added
- **Packaging** — PyPI wheel bundles React UI; hatch build hook + publish CI gate
- **Installers** — unified `scripts/install.sh` / `install.ps1` (PyPI chain); `cairn doctor`
- **Agent setup** — `AGENT_SETUP.md`, `cairn setup-prompt`, multi-client `cairn mcp install`
- **Golden path** — bare `cairn` runs sync + dashboard
- **Docs** — rewritten README, docs tree, auto-generated `docs/cli.md`

### Changed
- **Version** — `4.0.0` across pyproject, UI, API health
- **Package layout** — `server/` + `ui/` only; CLI entry `server.cli:app`
- **Database** — fresh v4 schema at `.cairn/cairn.db` (no v3 ledger migration)

### Removed
- Legacy `cairn/` Python package (snapshot on git tag `v3-final`)
- `tests/_legacy/`, stale docs under `docs/spec`, `docs/superpowers`, `docs/guides`, `docs/reference`
- v3 CLI verbs (`init`, `validate`, `build`, `profile`, …)

### Breaking
- v3 `ledger.db` is not migrated — re-run `cairn sync` to ingest logs. See [docs/legacy-v3.md](docs/legacy-v3.md).

---

## v0.1.0 (2026-07-04)

First v4 release — trace-native observability, measured self-improvement, and a 12-page React UI.

### Wave 1 — Analyzers
- Incremental analyzer views: context regions, difficulty, fingerprint (AMDM), diagnose, outcomes
- SQLite repos and append-only migrations under `server/store/`
- Ported tests for regions, fingerprint, diagnose, outcomes, difficulty

### Wave 2 — Detectors
- Modular insight detectors in `server/improve/detectors/` (13 rules)
- Evidence chains and insight lifecycle (new → ack → fixed / regressed)
- Improve engine wiring with stale/fixed marking

### Wave 3 — Charts + Shell
- React field-notebook UI shell: Waypoint rail, plaque topbar, command palette
- visx chart kit (sparkline, gauge, radar, control chart, stacked area, waterfall)
- TanStack Query + SSE client for live updates

### Wave 4 — Pages
- All 12 UI pages: Overview, Sessions, Session detail, Context, Agents, Behavior, Quality, Insights, Optimize, Live, Search, Settings
- Waterfall with subagent swimlanes and replay scrubber
- Optimize station board (proposed → applied → measuring → verdict)

### Wave 5 — E2E + Quality Gates
- Playwright smoke tests (Overview→Sessions→replay, insight ack, live SSE)
- Waterfall perf test (10k spans), initial JS bundle budget in CI
- OpenAPI type generation from `/api/openapi.json`
- CI: ruff, mypy, pytest, UI typecheck/build, CDN-grep

### Wave 6 — Docs + Cleanup
- Rewrote getting-started, concepts; added adapters, api, ui-tour, optimize, legacy-v3 docs
- Fixed `ledger.db` → `cairn.db` in configuration reference and README architecture

### Added (cross-cutting)
- v4 trace-native data model with ingest adapters and OTLP receiver
- FastAPI read API, action registry, CLI parity (`server/cli.py`), MCP stdio server (six tools)
- Local store at `.cairn/cairn.db` (replaces v3 `ledger.db`)

### Changed
- Rewrote Cairn around OpenTelemetry-aligned spans, provenance-backed insights, and measured optimize loop
- CLI entry point: `cairn` → `server.cli:app` (v3 `cairn/cli/main.py` no longer installed)
