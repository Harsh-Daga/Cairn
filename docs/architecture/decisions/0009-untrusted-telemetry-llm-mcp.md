# ADR 0009: Untrusted telemetry, optional LLM, and MCP boundaries

Status: accepted for 1.2.0

## Context

Prompts, tool output, files, OTLP, archives, regression bundles, and peer MCP descriptions are
attacker-controlled data.

## Decision

- Untrusted content is typed data, never system/developer policy, HTML, Markdown authority, SQL,
  shell, or approval.
- Deterministic offline analysis is the default.
- Optional model calls keep trusted policy/approved intent structurally separate from
  provenance-labeled content; receive no tools, filesystem, secrets, or further network
  capability; and return a bounded schema rendered as text/data.
- Every egress requires preview/consent and a privacy-minimized ledger record.
- MCP defaults to stdio/read-only. Any HTTP transport is loopback-only with a launch secret plus
  Host/Origin validation and no persistent URL tokens.
- Suggested commands/mutations require a separate explicit approval boundary.

## Consequences

Model suggestions cannot upgrade deterministic evidence status. Hostile-content fixtures cover
every import/export/analysis boundary.
