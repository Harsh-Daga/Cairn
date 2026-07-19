# Performance and scale

Cairn has deterministic generated datasets, stable structural budgets, and opt-in timing
benchmarks. The measurements on this page are engineering evidence from one machine, not
cross-platform guarantees or marketing claims.

## Dataset profiles

The generator writes a migrated SQLite ledger on demand; no large database binary is committed.
The clock, identifiers, distribution, and row contents are fixed.

| Profile  | Traces |  Spans | Widest trace |
| -------- | -----: | -----: | -----------: |
| `small`  |    100 |    595 |          100 |
| `medium` |  1,000 |  5,495 |          500 |
| `large`  | 10,000 | 52,495 |        2,500 |

Generate a ledger or run the backend benchmark:

```bash
uv run python scripts/benchmark.py generate \
  --profile large \
  --workspace /tmp/cairn-benchmark

uv run python scripts/benchmark.py run \
  --profile large \
  --workspace /tmp/cairn-benchmark \
  --samples 7 \
  --include-static \
  --output-json test-results/performance.json
```

The `run` command regenerates the selected profile before measuring cold application construction,
first and unchanged incremental ingest, warm representative endpoints, payload sizes, peak process
RSS, and static export. Run it on an otherwise idle machine. Its p50/p95 values use local wall-clock
samples and are expected to vary with hardware and load.

Build and measure the browser separately:

```bash
uv run python scripts/build_ui.py build
uv run python scripts/check_bundle_size.py

# In another terminal, serve the generated large workspace on this loopback URL.
uv run cairn ui --workspace /tmp/cairn-benchmark --port 8799 --no-open

cd ui
CAIRN_BENCHMARK_URL=http://127.0.0.1:8799 node scripts/benchmark.mjs \
  > ../test-results/browser-performance.json
```

The browser script uses the repository's bundled Playwright Chromium. It reports session readiness,
a 50-row table scroll, wide-trace readiness, replay interaction, mounted waterfall rows, and
console errors. It never contacts an external service.

## Recorded 1.2 engineering sample

The checked-in reports are
[`v1.2.0-performance-results.json`](plans/v1.2.0-performance-results.json) and
[`v1.2.0-browser-performance-results.json`](plans/v1.2.0-browser-performance-results.json).
They were recorded on 2026-07-18 using Python 3.11.15 on an 8-logical-CPU Apple arm64 machine.

| Backend journey on the large profile |     p50 |      p95 |  Response |
| ------------------------------------ | ------: | -------: | --------: |
| Health                               |  1.1 ms |   1.2 ms |      33 B |
| Overview, 30 days                    | 23.8 ms |  79.2 ms |   1.4 KiB |
| Quality, 30 days                     | 52.5 ms |  70.6 ms | 283.3 KiB |
| Context regions, 30 days             | 32.5 ms |  32.7 ms |     473 B |
| Search                               | 75.2 ms |  76.0 ms |   7.4 KiB |
| Trace list, 200 rows                 | 16.0 ms |  16.9 ms |  76.3 KiB |
| 2,500-span trace detail              | 98.2 ms | 110.7 ms |  3.12 MiB |
| 2,500-span replay                    | 98.8 ms | 114.0 ms |  2.30 MiB |

Cold application construction was 610.2 ms. The generated database was 32.19 MiB and took 1.65
seconds to create. A first ingest of the fixed adapter fixture took 104.9 ms; an unchanged
incremental pass took 0.16 ms and correctly skipped parsing. The process high-water mark was 105.66
MiB.

The curated static snapshot captured the most recent 1,000 of 10,000 trace details, wrote 2,064
payloads totaling 48.47 MiB in 12.76 seconds, and reached a 108.36 MiB process high-water mark. Its
manifest declares both the captured and total trace counts. A static snapshot is a bounded viewing
artifact, not a full data-portability archive.

| Browser journey                              |   Result |
| -------------------------------------------- | -------: |
| Sessions ready                               | 638.9 ms |
| Session rows                                 |       50 |
| Table scroll                                 |  61.1 ms |
| Wide trace ready, including lazy route chunk | 865.0 ms |
| Replay interaction                           | 115.8 ms |
| Mounted waterfall rows before/after replay   |  34 / 34 |
| Console errors                               |        0 |

The scale run found three defects that were fixed before recording these results: replay serialized
too many cumulative checkpoints, static export emitted every trace detail, and the waterfall had no
bounded scroll viewport so all 2,500 rows mounted. Replay now adapts checkpoint density to a 5,000
serialized-span budget, static export declares and enforces a 1,000-detail cap, and the waterfall
virtualizer mounts only its visible window. Route-level splitting reduced the server build to 28
JavaScript is enforced in both delivery forms: route-split HTTP assets have separate entry and
total gzip ceilings, while the `file://` snapshot has a dedicated single-IIFE gzip ceiling. The
IIFE must inline lazy routes for direct-file compatibility, so its uncompressed Vite warning
threshold is distinct from—and backed by—the stricter release-gate gzip budget in
`scripts/check_bundle_size.py`.

The 2026-07-18 Session Diff build measured 82,499 bytes for the HTTP entry, 210,199 bytes across 31
HTTP chunks, and 220,601 bytes for the static IIFE, all gzip with deterministic timestamps. A
2026-07-19 local rebuild measured ~83.5 KiB entry, ~231.7 KiB HTTP total across 37 chunks, and
~233.2 KiB static IIFE gzip. The static IIFE gzip ceiling is therefore **240 KiB** (separate from
the 150 KiB entry / 350 KiB HTTP-total ceilings) because the file snapshot must inline lazy routes.

## Automated budgets

Pull-request CI enforces deterministic properties rather than noisy wall-clock results:

- exact profile trace/span/wide-trace counts and repeatable logical query results;
- a large generated database below 64 MiB;
- bounded query pages and 200-row trace-list behavior;
- 2,500-span detail and replay responses below 4 MiB each;
- correct flattening of 10,000 waterfall rows, with the Python reference check below 500 ms;
- iterative flattening of a 5,000-level parent chain without JavaScript call-stack recursion;
- diff alignment switches from quadratic LCS above 1,000,000 sequence cells, caps input at 2,000
  spans per side, and progressively mounts 200 UI rows at a time with an explicit limitation;
- JavaScript entry gzip below 150 KiB and total JavaScript gzip below 350 KiB;
- a static-export capture limit whose manifest distinguishes captured from total traces.

These checks live in `tests/test_performance_fixtures.py`, `tests/test_waterfall_perf.py`,
`ui/src/test/waterfallLayout.test.ts`, `tests/test_static_export.py`, and
`scripts/check_bundle_size.py`.

The scheduled/manual performance workflow records the timing report as an artifact instead of
failing on timing drift. Initial review targets are cold start below 1.5 seconds; representative
endpoint p95 below 250 ms, except wide detail/replay below 500 ms; a 1,000-detail static export below
30 seconds, 96 MiB output, and 256 MiB peak RSS; browser sessions/wide-detail readiness below
1.5/2 seconds; scroll/replay below 200/300 ms; and fewer than 100 mounted waterfall rows. These are
triage thresholds for comparable runners, not supported-platform promises.

Resource Shield and portability facilities (circuit breakers, quarantine, egress ledger, reference
mode, archive, lifecycle) landed in Phase 6. Their **behavior** is covered by pytest
(`test_circuit_breakers`, `test_archive`, `test_egress`, `test_reference_mode`, `test_jobs`,
`test_watcher`, `test_lifecycle`, `test_resources`). Long-running idle/WAL/throughput *timing*
trends remain on the scheduled/manual `performance.yml` workflow rather than PR wall-clock gates.

## Content-addressed storage assessment (T06-06)

1.2.0 does **not** ship a content-addressed blob store. ADR
[0013](architecture/decisions/0013-content-addressed-storage-deferral.md) defers CAS until a ledger
shows measured benefit; search stays on canonical columns after FTS retirement
([0012](architecture/decisions/0012-query-indexes-and-search-storage.md)).

Assess a workspace or generated profile:

```bash
uv run python scripts/benchmark.py assess-dedup --profile large --output-json test-results/dedup.json
```

The report estimates text-hash reuse and rough inline-character savings, states that `spans_fts` is
absent, and never recommends adopting CAS inside the 1.2.0 release line.

## Accelerated resource soak (T06-10)

```bash
uv run python scripts/benchmark.py resource-soak \
  --profile small \
  --soak-seconds 8 \
  --sse-clients 4 \
  --output-json test-results/resource-soak.json
```

This samples three short windows — idle RSS/threads, in-process EventBus publish/subscribe load
with `/api/health` latency, and sync job-action latency — plus a collection-mode flip. It is an
accelerated triage probe (`cairn.resource_soak.v2`), not an eight-hour idle soak or multi-client
HTTP SSE load claim. Behavior coverage for watcher/jobs/SSE backpressure remains in pytest;
scheduled `performance.yml` can attach soak JSON as an artifact.
