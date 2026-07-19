# ADR 0013: Content-addressed storage deferral and search consistency

- Status: accepted for 1.2.0
- Date: 2026-07-19

## Context

Coding-agent traces often repeat tool schemas, instructions, and tool results. Revamp §6.6 asked for
an investigation into content-addressed storage (CAS): hash repeated content, store one bounded blob
with references, keep FTS/privacy explicit, support refcounts or reachability cleanup, preserve
evidence hashes after stripping, verify collision handling, and benchmark CPU vs disk savings.

Separately, `spans_fts` was created historically but never transactionally maintained by production
ingest (ADR 0012). Maintaining two divergent search sources is unacceptable.

## Decision

1. **FTS:** Keep the ADR 0012 retirement. Search uses bounded scans over canonical
   `traces`/`spans` columns. There is no second search index to keep consistent. Rebuild of a
   derived FTS index is not offered; UI/CLI copy must not claim an FTS index exists.

2. **Hashes without CAS:** Continue storing `text_hash` / `args_hash` on spans and region
   `content_hash` values. Storage modes (Metrics / Balanced / Forensic / Reference) already control
   raw text retention while preserving hashes for evidence (ADR 0011).

3. **CAS deferred:** Do **not** ship a blob table, refcount GC, or content-addressed rewrite in
   1.2.0. Adopt CAS only after a measured dedup assessment shows worthwhile savings on
   representative ledgers (see `scripts/benchmark.py assess-dedup` and
   [performance](../../performance.md)).

4. **Collision policy (when CAS lands later):** Prefer SHA-256 content digests; on collision of
   digest with differing bytes (theoretical), refuse to alias and store a distinct row keyed by
   digest+length or quarantine the write. Tiny values stay inline when blob metadata would exceed
   savings.

## Consequences

- 1.2.0 disk growth is managed by storage modes, strip/lifecycle, reference mode, and soft budgets
  — not by CAS.
- Assessment evidence can revisit CAS without blocking the release.
- Search privacy/deletion semantics remain tied to the single canonical span row.
