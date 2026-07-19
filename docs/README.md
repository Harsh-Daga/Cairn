# Cairn documentation

Cairn is a local-first observability workspace for AI coding agents. It ingests local agent sessions, analyzes cost and quality, and helps you investigate or improve recurring behavior.

## Start here

- [Live static demo](https://harsh-daga.github.io/Cairn/) — read-only Pages snapshot (see [Pages](pages.md)).
- [Examples](../examples/README.md) — deterministic demo, CI gate, OTLP, MCP, export/archive.
- [Getting started](getting-started.md) — install Cairn, sync a workspace, and open the dashboard.
- [CLI reference](cli.md) — every supported command and registered action.
- [Configuration](configuration.md) — server, workspace, budgets, tests, and model-pricing settings.
- [Generated configuration reference](configuration-reference.md) — typed keys and defaults.
- [Time ranges](time-ranges.md) — presets, custom ranges, timezone, and static-snapshot semantics.

## Use the product

- [Concepts](concepts.md) — traces, spans, views, insights, and experiments.
- [UI tour](ui-tour.md) — every dashboard page and its data source.
- [Adapters](adapters.md) — supported agents and how to add an adapter.
- [OTLP ingest](otlp.md) — send OpenTelemetry traces to Cairn.
- [Optimize loop](optimize.md) — propose, apply, measure, and evaluate instruction changes.
- [Verification receipts](verification.md) — claim–evidence receipt v1, debt, rebuild, CLI/API/MCP.
- [Local regressions](regressions.md) — session-to-regression artifacts (create/validate/export; no execution).
- [Advisory policies](policy.md) — typed path/command risk rules (observe ≠ block).
- [Resource shield](resource-shield.md) — local disk inventory, soft budget, descriptive forecast.
- [Privacy](privacy.md) — local-first controls, storage, egress, sharing limits.
- [Data lifecycle](data-lifecycle.md) — retention, dry-run cleanup, backup/restore, integrity.
- [Offline pricing](pricing.md) — bundled rates, overrides, staleness (never auto-download).
- [Portable archive](archive.md) — versioned `cairn.archive.v1` export/import/inspect.
- [Egress ledger](egress.md) — privacy-minimized Cairn-initiated network accounting.
- [Roadmap](roadmap.md) — future opt-in community concepts and their privacy constraints.
- [Releasing](releasing.md) — pointer to the tag-driven release process.
- [Research: competitive landscape](research/competitive-landscape.md) — differentiation note.
- [Research: user needs](research/user-needs.md) — jobs-to-be-done synthesis.
- [v1.2.0 final evidence report](plans/v1.2.0-final-report.md) — FIN-02 19-part readiness dossier.
- [CI gates](ci.md) — use Cairn quality and cost checks in automation.
- [Testing and coverage](testing.md) — behavior suites, branch baselines, and changed-line ratchets.
- [Performance and scale](performance.md) — deterministic datasets, reproducible measurements, and budgets.
- [Accessibility](accessibility.md) — theme behavior, color semantics, and validation scope.
- [Browser support](browser-support.md) — tested engines, touch/reflow, and OS preference policy.

## Integrate and operate

- [API overview](api.md) — HTTP endpoints, actions, SSE, and error behavior.
- [API domain boundaries](architecture/api-domains.md) — stable Python facades and model/builder ownership.
- [CLI domain boundaries](architecture/cli-domains.md) — stable entry point and command ownership.
- [Demo and adapter boundaries](architecture/demo-adapter-boundaries.md) — deterministic fixtures and untrusted parsing stages.
- [UI primitive boundaries](architecture/ui-primitives.md) — shared interaction contracts and ownership.
- [ADR 0013: CAS deferral](architecture/decisions/0013-content-addressed-storage-deferral.md) — content-addressed storage deferred; FTS stays retired.
- [v1.2.0 hypothesis cards](plans/v1.2.0-hypothesis-cards.md) — deferred P2 EXP/RES scope.
- [Accuracy](../ACCURACY.md) — token-estimation methodology and current measurements.
- [Security](../SECURITY.md) — security reporting and deployment boundaries.
- [Support](../SUPPORT.md) — where to get help or report a problem.

The documentation describes the current 1.1.1 public beta: a FastAPI backend and React dashboard backed by the local SQLite ledger. It intentionally does not document retired package layouts or obsolete CLI commands; README and generated CLI command rows are checked against the registered Typer surface in CI.
