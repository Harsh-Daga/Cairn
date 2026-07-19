# ADR 0010: Portable evidence/archive schema

Status: accepted for 1.2.0

## Context

Current trace bundles are neither a lossless workspace archive nor a versioned regression/receipt
format.

## Decision

- The archive envelope includes schema/producer versions, UTC/timezone semantics, retention mode,
  provenance, manifest, per-file checksums, and privacy inventory.
- JSON domain files use canonical deterministic serialization; attachments use allowlisted
  relative names and declared media/size.
- Readers support the current and previous major schema, preserve/report safe unknown fields, and
  reject incompatible newer semantics without reinterpretation.
- Import is offline, dry-run first, streaming/bounded, path-safe, duplicate-aware, and reports
  partial failures without applying an ambiguous remainder.
- Metadata-only/scrubbed modes preview included classes and sizes.
- OTLP remains supported with documented Cairn-specific round-trip loss.

## Consequences

ZIP is a transport container, not a trust boundary; entry count, ratio, nesting, size, symlink,
duplicate, and path limits are mandatory.
