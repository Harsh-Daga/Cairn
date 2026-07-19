# Offline model pricing

Cairn prices tokens from a **bundled offline** table plus optional local overrides. It never
silently downloads prices.

## Bundled table

Path: `server/data/model_prices.json`

| Field | Meaning |
| --- | --- |
| `source` | Provenance label for the snapshot |
| `version` | Snapshot version (YYYY.MM.DD style) |
| `effective_date` | Date the rates were believed current |
| `models[].match` | Longest-prefix match key |

## Local overrides

Prefer unified config:

```toml
[pricing]
stale_after_days = 90

[pricing.overrides.gpt-example]
input_per_mtok = 1.0
output_per_mtok = 4.0
```

Legacy `~/.cairn/prices.toml` and `.cairn/prices.local.toml` remain read-compatible.

## Visibility

| Surface | Behavior |
| --- | --- |
| `CostBreakdown.pricing_kind` | `matched` / `override` / `unknown` |
| Overview `data_notes` | `stale_pricing` when bundled table exceeds `stale_after_days` |
| `cairn doctor` | Model pricing check (warns when stale) |
| `cairn action pricing_status` | Full provenance JSON |
| `cairn action pricing_refresh_preview` | Explicit preview stub — **never downloads** |
| `cairn privacy` | Includes pricing summary |

Unknown models produce zero cost with `pricing_kind=unknown` (mapped to `cost_source=absent` at
ingest when total is 0). Use overrides for models missing from the table.
