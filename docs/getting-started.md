# Getting started

## Install

| Method | Command |
|--------|---------|
| **uv tool** (recommended) | `uv tool install cairn-workspace` |
| **pip** | `pip install cairn-workspace` |
| **curl** | `curl -LsSf https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/scripts/install.sh \| sh` |

Pin a version: `CAIRN_VERSION=1.0.0` with the install script, or `uv tool install cairn-workspace==1.0.0`.

Verify: `cairn doctor`

## Agent-driven setup

Paste the bootstrap block from the [README](../README.md) or run `cairn setup-prompt`, then follow [AGENT_SETUP.md](../AGENT_SETUP.md).

## First ten minutes

```bash
cd your-repo
cairn                    # sync + open dashboard (or: cairn sync && cairn ui)
cairn insights           # list active detector findings
cairn doctor             # verify install
```

1. **Overview** — KPIs, sparklines, narrative sentences for the last 30 days.
2. **Sessions** — filter traces, open waterfall + replay scrubber.
3. **Insights** — acknowledge findings; trace evidence chains.
4. **Optimize** — review proposals, apply with approval, watch holdout verdict.
5. **Settings** — rescan adapters, export bundle, install MCP.

Screenshots: [README § What it looks like](../README.md#what-it-looks-like).

## Manual sync

```bash
cairn sync
cairn sync --source claude_code
cairn sync --workspace /path/to/repo
```

## Start the UI

```bash
cairn ui                          # default 127.0.0.1:8787, opens browser
cairn ui --no-open --port 8788
```

## Supported agents

See the [adapter table in README](../README.md#supported-agents) and [adapters.md](adapters.md).

## Project layout

```
your-repo/
├── .cairn/
│   ├── cairn.db          # SQLite traces/spans/insights/experiments
│   ├── backups/          # instruction-file backups from optimize apply
│   └── exports/          # scrubbed bundles
├── AGENTS.md / CLAUDE.md # optimize targets
└── (Cairn installs as a tool — no vendor copy required)
```

## Next steps

- [Concepts](concepts.md) — traces, spans, views, experiments
- [UI tour](ui-tour.md) — all pages + keyboard map
- [CLI reference](cli.md)
- [Optimize loop](optimize.md)
