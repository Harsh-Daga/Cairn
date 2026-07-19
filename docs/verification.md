# Verification receipts

Cairn builds a deterministic **verification receipt** (`cairn.receipt.v1`) from recorded
outcomes and spans. A receipt is evidence about what the session claimed and what was observed —
not a cryptographic attestation and not a test runner.

## What a receipt contains

| Field | Meaning |
|-------|---------|
| Status | `verified` / `failed` / `debt` / `unverified` / `unknown` |
| Intent | First-user / outcome intent summary when present |
| Requirements | Transparent requirement rows derived from outcomes |
| Debt | Score and active components with explanations |
| Timeline | Ordered verification-relevant events from spans/outcomes |
| Limitations | Honest gaps (missing data, unavailable claim ledger in v1) |
| Content hash | SHA-256 of the deterministic receipt body |

Claim-level rows are intentionally absent in receipt v1. Absence of a claim is **not** labeled
unsupported or contradicted.

## Surfaces

| Surface | How |
|---------|-----|
| UI | Session Detail → Receipt tab |
| API | `GET /api/traces/{trace_id}/receipt` |
| CLI | `cairn receipt <trace_id> [--json]` |
| Action | `verification_rebuild` / `cairn action verification-rebuild` |
| MCP | `cairn_verification_status` (summary + remaining checks) |

Rebuild persists a snapshot when the content hash changes; reads can always recompute from the
ledger.

## Honesty limits

- Estimated or missing outcomes produce debt/unknown states rather than invented success.
- Receipts do not execute setup or verification commands.
- Default receipts scrub prompts, secrets, usernames, and absolute paths.
- Portable regressions may carry inferred verification *hints*; they are not run by Cairn.
  See [regressions](regressions.md).

## Related

- Schema storage: [data model](data-model.md#verification-receipts)
- UI placement: [UI tour](ui-tour.md)
- Policy risk on receipts: [policy](policy.md)
- Archive domain: [archive](archive.md)
