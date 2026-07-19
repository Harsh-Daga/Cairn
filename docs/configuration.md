# Configuration

Cairn resolves one typed configuration model. Precedence is:

1. an explicitly supplied CLI option;
2. a `CAIRN_*` environment variable;
3. `<workspace>/.cairn/config.toml`;
4. `~/.config/cairn/config.toml`;
5. the schema default.

Workspace files are optional and override the user file only for that workspace. Unknown keys
passed to the CLI/action and invalid values fail with an actionable error. Existing comments and
unrelated keys are retained by scalar mutations. Writes use owner-only permissions and atomic
replacement. See the [generated key reference](configuration-reference.md).

## Server settings (env)

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_HOST` | `127.0.0.1` | Bind address (loopback only unless `--token`) |
| `CAIRN_PORT` | `8787` | HTTP port |
| `CAIRN_TOKEN` | — | Required for non-loopback bind; protects every route with Bearer or browser-cookie auth |
| `CAIRN_WORKSPACE_ROOT` | cwd | Active workspace |
| `CAIRN_OUTCOME_REVERT_WINDOW_HOURS` | `24` | Same-file revert/fixup detection window (1–168h) |
| `CAIRN_LIMITS_FIVE_HOUR_TOKENS` | — | Plan-window token limit |
| `CAIRN_OPTIMIZE_AUTO` | `false` | Enable configured automatic optimize behavior |
| `CAIRN_OPTIMIZE_BACKEND` | — | Local or explicitly consented reflector backend |

## config.toml sections

| Section | Keys | Purpose |
|---------|------|---------|
| `[limits]` | `five_hour_tokens` | Plan-window token gauge limit |
| `[budgets]` | `monthly_usd`, `weekly_usd`, `daily_usd`, `min_quality` | Spend ceilings, burn projections, Overview attention, `cairn stats`, quality check gates |
| `[policy]` | `path_risks`, `commands`, `required_checks`, `exceptions`, … | Advisory path/command risk (observe ≠ block); see [policy.md](policy.md) |
| `[collection]` | `mode` (`manual`/`efficient`/`live`) | Backend auto-sync only; independent of browser SSE Live updates |
| `[resources]` | `soft_budget_bytes`, `max_file_bytes`, `max_parse_ms`, `max_consecutive_failures` | Soft disk budget + ingest circuit breakers (see [resource-shield.md](resource-shield.md)) |
| `[jobs]` | `max_workers`, `max_queued`, `result_ttl_sec`, `default_timeout_sec` | Bounded async action executor (see [jobs.md](architecture/jobs.md)) |
| `[storage]` | `mode`, `text_inline_max`, `scrub_at_ingest`, `balanced_retain_days` | Metrics/Balanced/Forensic raw text policy (see [storage-modes.md](storage-modes.md)) |
| `[resources]` | `soft_budget_bytes` | Soft local disk budget; warns only — never deletes |
| `[optimize]` | `auto`, `backend`, `holdout` | Optimize loop tuning |
| `[tests]` | per-project commands | Outcome test runner (`[tests.default]`) |
| `[diagnose]` | cascade/changepoint tunables | Failure localization |
| `[mcp]` | `auto_install` | Auto-write MCP on first run |
| `[pricing]` / `[pricing.overrides.<model>]` | `stale_after_days`, price-row fields | Offline pricing + local overrides (see [pricing.md](pricing.md)) |

Example:

```toml
[limits]
five_hour_tokens = 500000

[tests]
default = "pytest -q"

[budgets]
min_quality = 0.65

[pricing.overrides.gpt-example]
input_per_mtok = 1.0
output_per_mtok = 4.0
```

## Workspace data

| Path | Contents |
|------|----------|
| `.cairn/cairn.db` | SQLite store |
| `.cairn/backups/` | Instruction file backups |
| `.cairn/exports/` | Scrubbed export bundles |

## CLI config

```bash
cairn config get server.port
cairn config set server.port 8788
cairn config set budgets.weekly_usd 25 --scope workspace --workspace .
cairn config unset budgets.weekly_usd --scope workspace --workspace .
cairn config list
cairn action config_set --params-json \
  '{"operation":"get","key":"server.port"}'
```

`get` and `list` report the winning source. Keys containing authentication tokens, passwords,
secrets, or API keys are redacted unless `--show-secrets` is explicitly supplied. Avoid printing
secrets into shared logs even with that opt-in.

Legacy scalar names (`host`, `port`, `token`, `test_command`, `optimize_auto`, and
`five_hour_tokens`) remain accepted as aliases. Legacy `~/.cairn/prices.toml` and
`.cairn/prices.local.toml` remain read-compatible; new price overrides belong in the unified TOML.

Timezones used by dashboard and API ranges are request state, not a hidden global configuration
value. See [Time ranges and timezones](time-ranges.md).
