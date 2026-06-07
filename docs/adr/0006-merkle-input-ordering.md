# ADR 0006: Merkle rollup input ordering

**Status:** Accepted  
**Date:** 2026-06-07  
**Charter:** §9 (`rendered_inputs_hash`), R1, R17 #2–#3

## Context

`rendered_inputs_hash(N)` rolls up digests of all consumed sources and upstream refs. The
spike sorts digests before hashing (order-independent fan-in). That matches reduce steps
where input order must not affect cache keys.

## Decision

1. **Default: order-independent.** `merkle_hash(d1, d2, …)` sorts digest strings
   lexicographically, then `sha256(canonical_json(sorted_list))`.
2. **Rationale:** reduce/fan-in steps consume an unordered set of upstream outputs; permuting
   `inputs` declaration order must not change the key.
3. **Future order-sensitive dependencies** must encode order explicitly in the digest list
   (e.g. a single composite digest per ordered slot) rather than relying on list order in
   `inputs`.

## Consequences

- `merkle_hash(a, b) == merkle_hash(b, a)` — pinned by property test.
- Map nodes use a single input digest per item (order trivial).
- If a step needs ordered inputs later, schema/ADR must add an explicit ordered digest field.
