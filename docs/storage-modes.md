# Content storage modes

Cairn retains **metrics** always. Raw `text_inline` retention is controlled by
`[storage].mode`:

| Mode | Raw text | Notes |
|------|----------|--------|
| `reference` | None (source-authoritative) | Cursors/hashes/metrics kept; detects source drift; not pure zero-copy |
| `metrics` | None | Hashes/tokens/cost/outcomes kept; transcript shows absence |
| `balanced` (default) | Truncated recent text | Age window via `balanced_retain_days` + `storage_strip` |
| `forensic` | Longest truncate cap | Privacy/disk warning; never default for team exports |

### Reference mode

Use when agent logs should remain the content authority:

```toml
[storage]
mode = "reference"
```

Cairn still stores cursors, hashes, and metrics — it does **not** claim zero-copy for those
fields. If a source file is missing or rewritten shorter, drift is recorded under
`.cairn/source_drift.jsonl` and surfaced via `cairn action source_drift_status`.

## Configuration

```toml
[storage]
mode = "balanced"
text_inline_max = 500          # optional; mode defaults apply when omitted
scrub_at_ingest = false        # optional secret/path scrub using export scrubbers
balanced_retain_days = 14
```

Upgrading to a more invasive mode (e.g. metrics → forensic) requires
`confirm_storage_upgrade=true` on `config_set` — no silent upgrades.

## Strip existing text

```bash
cairn action storage_strip --params-json '{"dry_run": true}'
cairn action storage_strip --params-json '{"limit": 5000}'
```

Strip nulls `text_inline` only; it is resumable and does not delete aggregates or hashes.

See also [resource-shield.md](resource-shield.md) and `cairn privacy --json`.
