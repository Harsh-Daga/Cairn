# Changelog

All notable changes to **cairn-workspace** follow [Semantic Versioning](https://semver.org/).

## [1.1.1] — 2026-07-14

### Fixed
- Publish the 1.1 release under a fresh patch version because PyPI permanently reserves filenames from deleted releases and rejected the reused 1.1.0 artifacts.

## [1.1.0] — 2026-07-14

### Added
- A 30-day money slide on first run and Overview with total spend, estimated wasted spend, ranked causes, concrete fixes, and a direct optimize action.
- Weekly terminal/UI recaps plus privacy-safe local “Agent Wrapped” PNG cards.
- Complete experiment lifecycle cards, human quality labels, quality component explanations, and score-to-human agreement diagnostics.
- Live detector-backed `cairn_should_i_stop`, cached `cairn_before_you_read` summaries, and privacy-minimal MCP consultation markers in session waterfalls.
- Adapter parse-health canaries, global format-change warnings, `cairn adapter doctor`, and fixture parse coverage for every built-in adapter.
- Strict, local-only `cairn optimize export-effects` artifacts for future opt-in community research.

### Changed
- Replaced invalid synthetic CUPED covariates with a documented difference in means and anytime-valid confidence sequence; experiment verdicts now use clustered effective sample sizes and model/task/version confound guards.
- Fingerprint joint-shock detection now requires 20 baseline sessions and uses Ledoit–Wolf covariance shrinkage; low-sample EWMA drift remains available and is labeled experimental.
- Every headline insight now carries estimated savings or an explicit missing-estimate reason plus a structured fix; non-actionable signals are separated as diagnostics.
- Quality outcomes now grade commit/test evidence and penalize same-file revert or fixup commits within the configured window.
- Existing trace exports now apply their advertised privacy scrubber instead of setting a scrubbed flag without redacting sensitive fields.

### Fixed
- Release versions, README claims, CLI docs, and installer paths are mechanically checked for consistency.
- Managed instruction blocks now refuse to overwrite user edits, back up before every apply, and support exact optimize reverts.
- MCP retains a read-only SQLite connection; consultation recording crosses into the ledger only through normal writable sync.

## [1.0.1] — 2026-07-13

### Changed
- Rebuilt the dashboard visual system around Manrope Variable typography, high-contrast violet and mint signals, denser cards, responsive navigation, and modern page-level copy.
- Added interactive point inspection, responsive gradient and dither chart surfaces, inline values, token allocation, cost-per-session, waste-rate, priority, and tail-risk views.
- Added `cairn upgrade` and Settings guidance for a one-command local update path.

### Fixed
- Active agent sessions now refresh their trace, spans, token totals, and end time as logs grow instead of retaining only the first ingested snapshot.
- The dashboard imports missed sessions in the background at startup, discovers new log files, and refreshes visible queries after live ingest events.
- Adapter-specific syncs such as `cairn sync --source codex` now honor the requested source and report updated sessions separately.

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

[1.1.1]: https://github.com/Harsh-Daga/Cairn/compare/v1.1.0...v1.1.1
[1.1.0]: https://github.com/Harsh-Daga/Cairn/compare/v1.0.1...v1.1.0
[1.0.1]: https://github.com/Harsh-Daga/Cairn/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/Harsh-Daga/Cairn/releases/tag/v1.0.0
