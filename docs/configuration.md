# Configuration

Cairn reads `~/.config/cairn/config.toml` for user-level settings. Runtime overrides use `CAIRN_*` environment variables (see `server/config.py`).

## Server settings (env)

| Variable | Default | Description |
|----------|---------|-------------|
| `CAIRN_HOST` | `127.0.0.1` | Bind address (loopback only unless `--token`) |
| `CAIRN_PORT` | `8787` | HTTP port |
| `CAIRN_TOKEN` | — | Required for non-loopback bind; protects every route with Bearer or browser-cookie auth |
| `CAIRN_WORKSPACE_ROOT` | cwd | Active workspace |

## config.toml sections

| Section | Keys | Purpose |
|---------|------|---------|
| `[limits]` | `five_hour_tokens` | Plan-window token gauge limit |
| `[budgets]` | `daily_usd`, `weekly_usd`, `min_quality` | Budget alerts + check gates |
| `[optimize]` | `auto`, `backend`, `holdout` | Optimize loop tuning |
| `[tests]` | per-project commands | Outcome test runner (`[tests.default]`) |
| `[diagnose]` | cascade/changepoint tunables | Failure localization |
| `[mcp]` | `auto_install` | Auto-write MCP on first run |
| `[pricing]` | `overrides` | Model price overrides |

Example:

```toml
[limits]
five_hour_tokens = 500000

[tests]
default = "pytest -q"

[budgets]
min_quality = 0.65
```

## Workspace data

| Path | Contents |
|------|----------|
| `.cairn/cairn.db` | SQLite store |
| `.cairn/backups/` | Instruction file backups |
| `.cairn/exports/` | Scrubbed export bundles |

## CLI config

```bash
cairn config set host 127.0.0.1
cairn action config_set --params-json '{"key":"port","value":"8788"}'
```

See `server/util/user_config.py` for diagnose defaults and validation.
