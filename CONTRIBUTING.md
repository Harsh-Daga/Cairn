# Contributing

Thanks for helping improve Cairn. The product is local-first: default flows make no silent
network calls, and public surfaces (CLI, API, UI, MCP, static export, docs) must describe the
same behavior.

## Supported versions

| Tool | Version |
|------|---------|
| Python | 3.11, 3.12, 3.13 (`requires-python >= 3.11`) |
| Node | 22+ (CI uses 22) |
| Package managers | `uv` (frozen lock) + `npm ci` (lockfile) |

## One-command bootstrap

```bash
git clone https://github.com/Harsh-Daga/Cairn.git && cd Cairn
uv sync --frozen --extra dev
npm --prefix ui ci
uv run python scripts/build_ui.py
uv run pytest -q
```

Then open a local dashboard against a disposable workspace:

```bash
uv run cairn demo --reset
uv run cairn ui --workspace "$HOME/.cairn-demo" --no-open
```

## Repo map

| Path | Role |
|------|------|
| `server/` | FastAPI app, CLI, ingest adapters, analyzers, SQLite store |
| `server/api/` | Routers, actions, schemas, payload domains (stable facades in `payloads.py` / `actions.py`) |
| `server/store/migrations/` | Numbered append-only SQL migrations |
| `ui/` | React/Vite dashboard |
| `docs/` | Product + architecture docs (index: `docs/README.md`) |
| `examples/` | CI-checked workflow samples |
| `scripts/` | Build, generate, release, and gate helpers |
| `.github/workflows/` | Deterministic CI, security, Pages, publish |

Architecture boundaries: [api-domains](docs/architecture/api-domains.md),
[cli-domains](docs/architecture/cli-domains.md),
[demo/adapter](docs/architecture/demo-adapter-boundaries.md),
[ui-primitives](docs/architecture/ui-primitives.md).

## Test matrix

| Layer | Command |
|-------|---------|
| Python | `uv run pytest -q` |
| Docs / CLI surface | `uv run pytest tests/test_docs.py tests/test_examples.py -q` |
| Lint / types | `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy --strict server` |
| UI unit | `npm --prefix ui run lint` · `format:check` · `typecheck` · `test` |
| UI coverage | `npm --prefix ui run test:coverage` + `uv run python scripts/check_coverage.py` |
| Browser | `npm --prefix ui run test:e2e` (Chromium full; Firefox/WebKit `@cross-browser`) |
| Adapter | `uv run pytest tests/adapter_conformance.py -q` |
| Release gate (full) | `uv run python scripts/release_check.py` |
| Release packaging-only | `uv run python scripts/release_check.py --packaging-only` |

Coverage policy and justified exclusions: [docs/testing.md](docs/testing.md).
CI layout: [docs/ci.md](docs/ci.md).

## Generated-file policy

Do **not** hand-edit generated artifacts. Regenerate through scripts, then commit the diff:

| Artifact | Command |
|----------|---------|
| `docs/cli.md` | `PYTHONPATH=. python scripts/gen_cli_docs.py` |
| UI API types + OpenAPI compat + `docs/api/generated.md` | `uv run python scripts/build_ui.py types` (or `npm --prefix ui run generate:api`) |
| Config reference | `uv run python scripts/generate_config_reference.py` |
| Accuracy tables | `uv run python scripts/gen_accuracy.py` |
| README/demo screenshots | `uv run python scripts/gen_readme_assets.py` (see below) |

Drift checks: `npm --prefix ui run check:api`, `tests/test_docs.py`, `scripts/release_check.py`.

## Dependency policy

- Python: edit `pyproject.toml`, then `uv lock` / `uv sync --frozen --extra dev`. No unpinned CI installs.
- UI: edit `ui/package.json`, then `npm --prefix ui install` so `package-lock.json` updates; CI uses `npm ci`.
- GitHub Actions: pin third-party actions to full commit SHAs (`tests/test_workflows.py`).
- No CDN URLs in product code (`tests/test_cdn_grep.py`). Runtime stays offline-capable.

## UI screenshots

README and `docs/assets/` media must come from the **real deterministic demo**, not mock art.

```bash
uv run cairn demo --reset
uv run cairn ui --workspace "$HOME/.cairn-demo" --no-open
uv run python scripts/gen_readme_assets.py
```

Use `--base-url` when the dashboard is not on the default port. Layout baselines under
`docs/assets/v1.2/baseline/` are deterministic captures for CI/layout checks.

## Migration checklist

When changing stored schema:

1. Add an append-only file under `server/store/migrations/` (never rewrite applied migrations).
2. Keep SQL and repository ownership inside `server/store/`.
3. Exercise fresh DB, upgrade from `tests/fixtures/db/pre-1.2.sqlite`, and repeated startup.
4. Confirm pre-migration backup behavior for existing user DBs ([data-model](docs/data-model.md)).
5. Update static export / archive domains if new tables are user-visible evidence.
6. Document destructive or retention behavior honestly (no silent deletion).

## API compatibility checklist

- Prefer additive OpenAPI / Pydantic schema changes; regenerate UI types.
- Keep action registry names stable; wire UI/CLI/MCP through registered actions.
- Preserve public CLI commands and MCP tool names; extend rather than rename.
- Static export must declare unsupported queries instead of inventing parity.
- Application errors use the standard envelope ([ADR-0003](docs/architecture/decisions/0003-openapi-generated-types.md)).

## Accessibility checklist

- Primary journeys target WCAG 2.2 AA ([docs/accessibility.md](docs/accessibility.md)).
- Keyboard-only paths for navigation, dialogs, and tables; visible focus.
- Theme tokens only — no hard-coded hex in components; verify light + dark.
- Charts/status must not rely on hue alone; keep text/icon alternatives.
- Run axe-covered e2e (`npm --prefix ui run test:e2e`) after UI changes.
- Prefer labels/names that make sense out of visual context.

## Privacy-safe fixtures

- Never commit real prompts, secrets, absolute home paths, or private repo contents.
- Prefer synthetic/deterministic fixtures under `tests/fixtures/` and `server/demo/`.
- Scrub absolute workspace roots in exports; review scrubbing as best-effort, not a proof.
- Adapter fixtures must be sanitized; conformance + privacy tests apply
  ([docs/adapters.md](docs/adapters.md)).
- Treat imported spans, MCP text, and tool output as **untrusted data**.

## Adapter PRs

1. Scaffold: `cairn adapter new my_agent` (or hand-add under `server/ingest/adapters/`).
2. Register via entry point / `server/ingest/registry.py`.
3. Add sanitized fixture under `tests/fixtures/ingest/`.
4. Pass `uv run pytest tests/adapter_conformance.py`.

One parser + one fixture + harness green is a mergeable adapter PR. Keep distinct upstream formats
in distinct parsing-stage modules when trust/I/O boundaries differ (Cursor is the reference split).

Demo data: edit `server/demo/scenarios.py` / `fixtures.py` / `improvement_fixtures.py`; keep
`server/demo/seed.py` as the facade; update `tests/test_demo.py` when canonical counts change.

## Style gates

- ~400 lines is a cohesion/review trigger, not a gameable hard limit — split by domain or document
  why a larger module stays cohesive.
- No SQL outside `server/store/`.
- Mutations through the action registry only (CLI/API/UI parity).
- Facades stay thin; put logic in domain modules.

## Pull requests

- Prefer one logical change per PR; keep diffs reviewable.
- Update docs/examples when CLI, API, or user-visible behavior changes.
- Add or update behavior tests for every compatibility-sensitive change.
- Do not commit, tag, or publish from exploratory agent tasks unless a maintainer asks.
- Release process is tag-driven and maintainer-only: [docs/releasing.md](docs/releasing.md),
  [docs/release.md](docs/release.md).

## Contribution map

| Area | Start here |
|------|------------|
| Docs / a11y labels | Focused Markdown or label fixes + `tests/test_docs.py` |
| Adapters | `server/ingest/adapters/` + fixtures + conformance |
| UI | `ui/src/` + Vitest + Playwright primary journeys |
| Backend / data | Migrations, action/CLI parity, bounds, untrusted input |
| Security / release | ADRs + maintainer docs; never change remote publish settings from a PR task |

Security reports: [SECURITY.md](SECURITY.md). Support: [SUPPORT.md](SUPPORT.md).
