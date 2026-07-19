# Privacy

Cairn is local-first: workspace telemetry lives under `<workspace>/.cairn/`, the default bind is
`127.0.0.1`, and default product flows make **no** outbound network calls.

## What may be stored

Coding-agent traces can include prompts, tool I/O, paths, repository metadata, and inferred
findings. Treat `.cairn/` and optional `~/.cairn/` as sensitive. Back up, share, and delete them
deliberately.

## Controls

| Control | Role |
|---------|------|
| Storage modes | `reference` / `metrics` / `balanced` / `forensic` — see [storage modes](storage-modes.md) |
| Resource shield | Disk inventory, soft budget, quarantine — [resource shield](resource-shield.md) |
| Lifecycle | Retention, dry-run cleanup, backup/restore — [data lifecycle](data-lifecycle.md) |
| Egress ledger | Cairn-initiated network accounting only — [egress](egress.md) |
| Archive / export | Scrubbed or metadata-only portable artifacts — [archive](archive.md) |
| Git privacy | Private path modes and exclude approval via doctor / Settings |

```bash
cairn privacy --json
cairn resource
cairn doctor
```

## Network honesty

- Opt-in reflector/provider calls require explicit consent and append `.cairn/egress.jsonl`.
- An empty egress ledger means *Cairn* did not initiate egress — not that other agents were silent.
- Non-loopback binds require a configured token; Host/Origin checks still apply.

## Sharing limits

Pattern-based scrubbing removes known credentials and absolute workspace roots. It cannot prove
arbitrary private text is safe. Review exports, archives, and regressions before sharing.

See also [SECURITY.md](../SECURITY.md) and the [threat model](security/threat-model.md).
