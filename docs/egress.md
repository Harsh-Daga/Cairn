# Egress ledger

Cairn records every **Cairn-initiated** network attempt in a privacy-minimized local ledger
(ADR-11). Default product flows leave the ledger empty and make no outbound requests.

## What is recorded

| Field | Notes |
| --- | --- |
| `timestamp` | UTC ISO-8601 |
| `trigger` | e.g. `reflector_provider` |
| `destination_origin` | `scheme://host` only (no path/query/credentials) |
| `purpose` | Short purpose string |
| `provider` | Backend id (`provider:openai`, …) |
| `field_classes` | Classes of data involved — never raw prompts |
| `byte_estimate` | Approximate request JSON size when practical |
| `consent_source` | e.g. `explicit_consent` |
| `success` / `error_class` | Outcome without response bodies |

**Never stored:** secrets, bearer tokens, API keys, raw prompts, or full payloads.

Path: `.cairn/egress.jsonl`

## Surfaces

```bash
cairn privacy --json          # includes egress summary
cairn action egress_status
cairn action egress_export
cairn doctor                  # informational entry count
```

Opt-in reflector provider calls (`reflector_run` with consent) append ledger rows. Preview
(`reflector_preview`) does not.

## Limitation

Cairn cannot observe traffic from unrelated agent processes (Cursor, Claude Code, etc.). An empty
ledger means *Cairn* did not initiate egress — not that the machine made no network calls.
