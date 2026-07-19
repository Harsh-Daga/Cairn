# ADR 0004: Detector consolidation

Status: accepted for 1.2.0

## Context

Retry, context, model, and tool-schema detectors overlap and can emit duplicate cards with
inconsistent evidence and estimates.

## Decision

- Canonical families are retry storm, context thrash, model mismatch, and stale tool schema.
- Existing detector IDs remain compatibility aliases/evidence producers; one family aggregator
  owns de-duplication and lifecycle.
- Every result has a versioned workspace/subject fingerprint, normalized trigger,
  confidence/coverage, `estimate_kind`, conservative estimate or unavailable reason, exact
  evidence IDs, and one structured next action.
- Drift, quality, and cost anomaly remain diagnostics unless evidence supports a cause.

## Consequences

Existing history stays readable while new runs stop flooding the board.
