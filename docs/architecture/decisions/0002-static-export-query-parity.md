# ADR 0002: Static-export query parity

Status: accepted for 1.2.0

## Context

The exporter materializes selected query filenames, while the client constructs arbitrary query
strings. Current Sessions/Search filenames do not match real requests, recap/diff are missing, and
raw payloads include sensitive fields.

## Decision

- A versioned manifest declares `captured_at`, data bounds, query capabilities, and unavailable
  live/mutation behavior.
- Export payloads use public DTOs plus an export privacy projection; raw domain objects and
  absolute paths are forbidden.
- Bounded filters/ranges evaluate locally from an exported normalized index where practical.
  Unsupported queries fail visibly and never fall back to unrelated data.
- File exports use relative assets and hash/adaptive routing.
- Controls consume capabilities and render honest read-only/unavailable states.

## Consequences

The export may grow by a bounded index but gains deterministic privacy and `file://` parity.
