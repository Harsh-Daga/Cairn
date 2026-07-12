# Changelog

All notable changes to **cairn-workspace** follow [Semantic Versioning](https://semver.org/).

The v4 rewrite was an internal codename. Cairn 1.0.0 is the first stable public release.

## 1.0.0 (2026-07-12)

First stable public release, superseding the placeholder `0.0.1` and mistaken internal `4.0.0` version.

### Added
- **Packaging** — PyPI wheel bundles React UI; hatch build hook + publish CI gate
- **Installers** — unified `scripts/install.sh` / `install.ps1` (PyPI chain); `cairn doctor`
- **Agent setup** — `AGENT_SETUP.md`, `cairn setup-prompt`, multi-client `cairn mcp install`
- **Golden path** — bare `cairn` runs sync + dashboard
- **Server lifecycle** — PID file under `$XDG_STATE_HOME/cairn/`; `cairn stop` reads it with port fallback
- **Docs** — rewritten README (absolute image URLs for GitHub + PyPI), docs tree, auto-generated `docs/cli.md`

### Changed
- **Version** — semver `1.0.0` replaces the placeholder and mistaken internal versioning
- **Package layout** — `server/` + `ui/` only; CLI entry `server.cli:app`
- **Database** — fresh schema at `.cairn/cairn.db` (no v3 ledger migration)

### Removed
- Legacy `cairn/` Python package (snapshot on git tag `v3-final`)
- v3 CLI verbs (`init`, `validate`, `build`, `profile`, …)

### Breaking
- v3 `ledger.db` is not migrated — re-run `cairn sync` to ingest logs. See [docs/legacy-v3.md](docs/legacy-v3.md).

---

## 0.0.1 (2026-07-04)

Initial PyPI publish (early placeholder). Upgrade to `1.0.0+` for the supported release.

---

## v0.1.0-dev (2026-07-04)

Internal development log for the v4 rewrite (pre-PyPI semver normalization).

### Wave 1 — Analyzers
- Incremental analyzer views: context regions, difficulty, fingerprint (AMDM), diagnose, outcomes
- SQLite repos and append-only migrations under `server/store/`

### Wave 2 — Detectors
- Modular insight detectors in `server/improve/detectors/`
- Evidence chains and insight lifecycle (new → ack → fixed / regressed)

### Wave 3 — Charts + Shell
- React field-notebook UI shell: Waypoint rail, plaque topbar, command palette
- visx chart kit, TanStack Query + SSE client for live updates

### Wave 4 — Pages
- All 12 UI pages with waterfall, replay scrubber, optimize station board

### Wave 5 — E2E + Quality Gates
- Playwright smoke tests, bundle budget in CI, OpenAPI type generation

### Wave 6 — Docs + Cleanup
- Rewrote getting-started, concepts; added adapters, api, ui-tour, optimize, legacy-v3 docs
