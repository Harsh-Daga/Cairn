# Getting started

## Install

| Method | Command |
|--------|---------|
| **uv tool** (recommended) | `uv tool install cairn-workspace` |
| **pip** | `pip install cairn-workspace` |
| **curl** | `curl -LsSf https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/scripts/install.sh \| sh` |

To pin a published version, set `CAIRN_VERSION=<published-version>` for the installer or run `uv tool install cairn-workspace==<published-version>`.

## Upgrade

Run `cairn upgrade` whenever you want the latest published Cairn release. It uses `uv tool` when available, then `pipx`, then the Python environment that launched Cairn. Use `cairn upgrade --check` to see the exact command first.

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

While `cairn ui` is running, Cairn automatically imports existing sessions at startup,
watches active logs, and rescans for newly created session files. Dashboard queries refresh
when live ingest events arrive. Use manual sync when the UI is not running or when scripting.

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
