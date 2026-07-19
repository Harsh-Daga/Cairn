# CI gates

Use Cairn in CI to block merges when agent quality regresses.

## Repository quality gates

The checked-in GitHub workflows use frozen `uv.lock` and `package-lock.json` resolution and pin
every external action to a reviewed commit. Pull-request CI is cancelable and receives read-only
repository permissions. Fast gates cover Python 3.11, 3.12, and 3.13; Ruff lint/format; strict
mypy; pytest; Prettier; ESLint TypeScript/React Hooks; TypeScript; Vitest; generated artifacts; and
the gzip bundle budget. A dedicated coverage job records Python/UI statement and branch coverage,
prevents the observed baseline from decreasing, and enforces 90% coverage on changed executable
lines. Integration jobs build and inspect archives, test a clean wheel, run the
seeded Chromium browser suite without skips, run tagged Firefox/WebKit core journeys, and open the
static snapshot from `file://` in all three engines. Demo Pages builds a `_site` preview artifact on
relevant pull requests; public deploy stays `workflow_dispatch`-only (see [pages.md](pages.md)).

The scheduled install workflow repeats clean-wheel smoke tests on Linux, macOS, and Windows.
Security automation and release permissions are documented in
[the OpenSSF gap report](security/openssf-gap-report-2026-07-17.md) and
[release process](release.md).

Local equivalents:

```bash
uv sync --frozen --extra dev
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict server
uv run pytest -q
npm --prefix ui ci
npm --prefix ui run lint
npm --prefix ui run format:check
npm --prefix ui run typecheck
npm --prefix ui test
npm --prefix ui run test:coverage
npm --prefix ui run test:e2e
uv run python scripts/check_coverage.py
# Packaging metadata + wheel doctor (also what CI integration job runs).
# Success line reads: release_check passed (packaging-only)
uv run python scripts/release_check.py --packaging-only
# Full local release gate before a release PR/tag (lint/tests/e2e/packaging/reproducibility).
# Success line reads: release_check passed (full gate)
uv run python scripts/release_check.py
uv run python scripts/check_reproducibility.py
```

## Basic gate

```bash
cairn sync
cairn check
```

`cairn check` runs the registered `check` action. Exit code is non-zero when gates fail.

## Threshold flags

```bash
cairn check --min-quality 0.65
cairn check --max-waste-pct 40
```

## GitHub Actions snippet

```yaml
- uses: astral-sh/setup-uv@v5
- run: uv tool install cairn-workspace
- run: |
    export PATH="$(uv tool dir --bin):$PATH"
    cd "${{ github.workspace }}"
    cairn sync
    cairn check --min-quality 0.6
```

## Tail cost gate (L4)

```bash
cairn check --max-tail-cost 25
```

Fails when projected worst-session cost over the next 1000 sessions exceeds the threshold (uses tail return-level estimate).

## Doctor in CI

After install:

```bash
cairn doctor --json
```

## Release publishing

Merging to `main` never publishes. An existing annotated semantic-version tag, either pushed or
selected by an approved manual dispatch, starts the build-once workflow. It creates and attests the
wheel, sdist, checksums, and CycloneDX SBOM; tests the downloaded artifacts; then uses the protected
PyPI Trusted Publishing environment and creates the GitHub Release from the same files. A final
public-index install verifies the published version. See [Release process](release.md).

## Related

- [Optimize loop](optimize.md) — experiment verdicts
- [Configuration](configuration.md) — `[budgets]` thresholds
- [Testing and coverage](testing.md) — baseline methodology, exclusions, and local commands
