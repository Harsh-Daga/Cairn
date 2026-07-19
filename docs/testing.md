# Testing and coverage

Cairn’s release gate favors behavior, contract, property, migration, hostile-input, accessibility,
browser, and integration tests. Coverage is a regression signal, not a claim that exercised code
is correct.

## Coverage ratchets

The observed baseline is committed in
`docs/plans/v1.2.0-coverage-baseline.json`. It was measured from the complete deterministic Python
suite and the complete Vitest suite with branch instrumentation. The gate:

- rejects a drop below either ecosystem’s observed statement or branch percentage;
- requires at least 90% line coverage on executable Python or UI lines added by a pull request;
- publishes the JSON, XML, LCOV, and UI HTML/data reports as CI artifacts;
- does not inflate the threshold by excluding low-coverage first-party modules.

Run the same checks locally:

```bash
uv run pytest -q --cov=server --cov-branch \
  --cov-report=json:test-results/coverage-python.json \
  --cov-report=xml:test-results/coverage-python.xml \
  --cov-report=lcov:test-results/coverage-python.lcov
npm --prefix ui run test:coverage
uv run python scripts/check_coverage.py
```

Pass `--base <git-ref-or-sha>` to the final command to enforce the changed-line ratchet. Without a
base it still enforces both repository floors.

## Justified exclusions

- `server/static/**` is generated bundled UI output; its source is tested under `ui/src`.
- `server/models/otlp_pb.py` is generated protobuf compatibility code.
- `ui/src/lib/generated/**` is generated from OpenAPI and has an independent drift/compatibility
  gate.
- `ui/src/test/**` is test infrastructure, not product code.
- `ui/src/main.tsx` is a two-line React bootstrap exercised by Playwright.
- `ui/src/vite-env.d.ts` is generated ambient type metadata.

New exclusions require a specific explanation in this document. Do not add broad `pragma:
no cover` markers to make a gate pass.

## Browser matrix

`npm --prefix ui run test:e2e` runs the complete Chromium suite plus the journeys tagged
`@cross-browser` in Firefox and WebKit. It fails when any configured engine is unavailable; CI
installs all three. The Chromium matrix includes axe in both themes, 320-pixel/200% reflow, touch,
reduced motion, forced colors, static `file://`, and hostile empty/disconnected states. Firefox and
WebKit cover Overview, custom time ranges, session detail, and the static snapshot.

The precise support promise and limitations are documented in
[Browser support](browser-support.md).
