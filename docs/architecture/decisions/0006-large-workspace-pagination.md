# ADR 0006: Large-workspace pagination and virtualization

Status: accepted for 1.2.0

## Context

Some endpoints/pages load large arrays; search slices after an unbounded SQL query.

## Decision

- Collections use stable server ordering, bounded cursor/offset pagination, and explicit totals or
  continuation markers.
- Default/max page sizes are 50/200. Negative offsets and unbounded limits are invalid.
- The UI virtualizes visible rows/spans while preserving semantic table/navigation alternatives.
- Large trace detail is summary-first and progressively paged.
- Exports stream/chunk under byte/item budgets.
- A deterministic 10,000-session fixture supplies query/interaction budgets.

## Consequences

Legacy `limit`/`offset` remain supported within bounds; cursor fields are additive.
