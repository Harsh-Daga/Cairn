# ADR 0001: Time range and timezone semantics

Status: accepted for 1.2.0

## Context

Most endpoints accept an unbounded integer `days`; calendar, timezone, prior-period, custom-range,
and static-snapshot semantics are undefined.

## Decision

- Canonical ranges are UTC instants in a half-open interval `[start, end)`.
- Requests accept either legacy `days` or complete `start`, `end`, and `timezone`; ambiguous or
  partial combinations are rejected.
- `days` remains a rolling duration for compatibility. Calendar presets resolve in the requested
  IANA timezone and convert to UTC. “Last 24 hours” remains distinct from “today.”
- Presets are 24h, 7d, 30d, and 90d. Prior comparisons use the immediately preceding
  equal-duration interval.
- Responses expose the resolved UTC range and requested timezone.

## Consequences

Existing clients keep `days`. Static snapshots declare capture/data bounds and never substitute a
different range.
