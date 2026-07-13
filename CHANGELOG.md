# Changelog

All notable changes to **cairn-workspace** follow [Semantic Versioning](https://semver.org/).

## [1.0.1] — 2026-07-13

### Changed
- Rebuilt the dashboard visual system around a clearer signal hierarchy, tactile dithered chart surfaces, richer metric cards, and refined navigation.
- Added interactive point inspection to the daily spend chart and clearer, information-rich dashboard framing.
- Added `cairn upgrade` and Settings guidance for a one-command local update path.

## [1.0.0] — 2026-07-13

The first public beta release of Cairn. It is intended for real-world use, with
the conservative release process, compatibility discipline, and quality gates
expected of a 1.0 line.

### Added
- **Packaging** — PyPI wheel bundles React UI; hatch build hook + publish CI gate
- **Installers** — unified `scripts/install.sh` / `install.ps1` (PyPI chain); `cairn doctor`
- **Agent setup** — `AGENT_SETUP.md`, `cairn setup-prompt`, multi-client `cairn mcp install`
- **Golden path** — bare `cairn` runs sync + dashboard
- **Server lifecycle** — PID file under `$XDG_STATE_HOME/cairn/`; `cairn stop` reads it with port fallback
- **Docs** — rewritten README (absolute image URLs for GitHub + PyPI), docs tree, auto-generated `docs/cli.md`
- **Live observability** — SSE heartbeat, bounded per-client queues, persisted live-watch preference, and Session Diff navigation
- **OTLP ingest** — HTTP protobuf and JSON trace ingestion backed by the official OpenTelemetry protobuf schema
- **Community health** — funding, support, code of conduct, pull-request template, and dependency update configuration

### Changed
- **Package layout** — `server/` + `ui/` only; CLI entry `server.cli:app`
- **Database** — fresh schema at `.cairn/cairn.db`
- **Security** — non-loopback servers require a token, with browser bootstrap support
- **Release automation** — merge-to-main publishing skips versions already present on PyPI and validates wheel installation, documentation links/assets, and GitHub YAML

### Fixed
- **SSE shutdown** — connected live clients no longer cause `cairn stop` to report a false failure
- **Packaging** — static UI assets are included exactly once in wheels and UI builds preserve the tracked static marker
- **CI** — optional MCP setup no longer fails `cairn doctor` in clean installation environments
- **Detector reliability** — all registered insight rules have regression coverage; zero-day re-billing windows no longer divide by zero
