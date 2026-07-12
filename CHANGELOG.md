# Changelog

All notable changes to **cairn-workspace** follow [Semantic Versioning](https://semver.org/). This branch prepares the first public release; it has not been published yet.

## [1.0.0] — Unreleased

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

### Changed
- **Package layout** — `server/` + `ui/` only; CLI entry `server.cli:app`
- **Database** — fresh schema at `.cairn/cairn.db`
