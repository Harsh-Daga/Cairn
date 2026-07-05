# Legacy v3 tree (`cairn/`)

The `cairn/` Python package is **legacy v3 code**, kept in the repository as a **port-only source** for algorithms and parsers that v4 reuses or is still migrating.

## What it is

| v3 (`cairn/`) | v4 (`server/`) |
|---------------|----------------|
| `ledger.db` | `cairn.db` at `.cairn/cairn.db` |
| `cairn/live/server.py` | `server/app.py` + `server/cli.py` |
| Monolithic CLI (`cairn/cli/main.py`) | Typer CLI with action registry |
| Session/event model | Trace/span (OTEL-aligned) model |

v4 is the supported architecture. New features belong in `server/` and `ui/`.

## Why it remains

- **Incremental port** — fingerprint math, waste taxonomy, parsers, and optimize logic were ported module-by-module from `cairn/` into `server/`. Some import paths still reach into `cairn/` during transition.
- **Do not delete** — the v4 server and tests may still import from `cairn/` until those ports finish. Removing the tree would break the build.

## CDN scan exclusion

CI runs `tests/test_cdn_grep.py` to ensure no external CDN URLs appear in shipped code. The `cairn/` directory is **excluded** from that scan (`SKIP_DIRS` includes `"cairn"`) because v3 contained third-party dashboard assets and CDN references that are not part of the v4 UI bundle.

The v4 UI (`ui/`) is fully bundled — no runtime CDN dependencies.

## What to use instead

| Task | Use |
|------|-----|
| Run dashboard | `cairn ui` → `server/app.py` |
| Sync logs | `cairn sync` → `server/ingest/` |
| Read docs | [Getting started](getting-started.md), [Concepts](concepts.md) |
| API | [API overview](api.md) |

## Migrating custom integrations

If you built against v3 APIs (`/v2/events`, `ledger.db`, `cairn show` with session IDs):

1. Point storage at `.cairn/cairn.db`
2. Use trace IDs from `cairn traces ls` or `/api/traces`
3. Subscribe to `/api/live/events` for SSE
4. Call mutations via `/api/actions/{name}` or matching CLI commands

The v3 CLI entry point (`cairn/cli/main.py`) is no longer installed — `pyproject.toml` maps `cairn` to `server.cli:app`.
