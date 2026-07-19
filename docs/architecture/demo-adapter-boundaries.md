# Demo and adapter boundaries

## Deterministic demo

`server.demo.seed` remains the supported import surface. Its implementation is divided by
responsibility:

- `scenarios.py` defines stable identities, counts, special trace indices, and pure trace scenarios;
- `fixtures.py` writes those scenarios into a migrated local ledger and owns reseed cleanup;
- `improvement_fixtures.py` writes the evidence, insights, state, experiment, and verdict journey.

Scenario generation accepts an explicit clock for deterministic tests. Production seeding uses the
current UTC date so the 30-day dashboard remains relevant, while identities and relative values
remain stable. Re-running seed cleanup is idempotent and preserves the canonical 120 traces, three
actors, four sources, failure cascade, multi-agent handoff, tail-cost outlier, and winning verdict.

## Adapter parsing

Adapter discovery stays in thin `*_adapter.py` wrappers. Parser modules decode untrusted upstream
records into typed intermediate sessions; the shared ingest normalizer/store pipeline remains the
only persistence path.

Cursor has two materially different sources and therefore two stages:

- `cursor_vscdb.py` locates and opens `state.vscdb` read-only, decodes composer/bubble values, and
  optionally joins transcript structure;
- `cursor_transcript.py` streams untrusted JSONL and normalizes messages, tool calls, artifacts, and
  sub-agent links;
- `cursor_models.py` owns the shared typed result and tool-name normalization;
- `cursor.py` is an identity-preserving compatibility facade.

Malformed JSON, missing tables/keys, absent optional transcripts, and unknown blocks remain
non-executable data. The read-only boundary is behavior-tested by comparing the database bytes
before and after parsing. Other built-in adapters already separate discovery wrappers from cohesive
parser-state modules and should only be split further when a real format or I/O boundary emerges.
