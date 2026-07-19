# Getting started

## Install

| Method                    | Command                                                                                                                                           |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **uv tool** (recommended) | `uv tool install cairn-workspace`                                                                                                                 |
| **pip**                   | `pip install cairn-workspace`                                                                                                                     |
| **Unix script**           | Download [`scripts/install.sh`](https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/scripts/install.sh), inspect it, then run `sh install.sh` |
| **PowerShell**            | Download [`install.ps1`](https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.ps1), inspect it, then run `& .\install.ps1`             |

The Cairn installer URLs above resolve directly to tracked files on the repository's `main`
branch. If `uv` is absent, those scripts use the official Astral installer at
`https://astral.sh/uv/install.sh` (Unix) or `install.ps1` (Windows). To pin a published
version, set `CAIRN_VERSION=<published-version>` for the installer or run
`uv tool install cairn-workspace==<published-version>`.

The bootstrap scripts download the official uv installer to a temporary file before executing it;
they never use `sudo`. For higher-assurance installation, install a reviewed uv version separately,
then set `INSTALL_UV=0`. `UV_INDEX_URL`/`PIP_INDEX_URL` and the standard proxy environment
variables are honored by the underlying package managers.

For a mirror or an offline machine:

```bash
UV_INDEX_URL=https://your-mirror.example/simple uv tool install cairn-workspace==<version>
uv tool install --offline cairn-workspace==<version>  # requires a warm uv cache
pip install ./cairn_workspace-<version>-py3-none-any.whl
```

## Upgrade

Run `cairn upgrade` whenever you want the latest published Cairn release. It uses `uv tool` when available, then `pipx`, then the Python environment that launched Cairn. Use `cairn upgrade --check` to see the exact command first.

Verify: `cairn doctor`

Re-running either installer upgrades or restores the same tool installation without deleting local
workspace data.

## Uninstall

Remove the executable with the package manager that installed it:

```bash
uv tool uninstall cairn-workspace
pipx uninstall cairn-workspace
python -m pip uninstall cairn-workspace
```

Uninstalling the package intentionally retains project `.cairn/` directories, databases, exports,
backups, and user state under the platform config/state directory. Review and remove those paths
manually only after exporting anything you need. `cairn doctor --json` identifies active paths
before uninstall.

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

## Empty workspace and deterministic demo

Overview distinguishes four cases instead of showing a blank dashboard:

- no local adapter streams discovered;
- streams discovered and ready to sync;
- logs attempted but not fully parsed, with a path to adapter diagnostics;
- the workspace has sessions, but none are inside the selected time range.

The first-run card shows the active private ledger path
`<workspace>/.cairn/cairn.db`, explains the account-free/zero-telemetry/loopback defaults, and
offers **Sync now**, **Scan again**, and an inline setup checklist. Discovery never edits agent or
MCP configuration.

**Load deterministic demo** creates a separate `~/.cairn-demo` workspace so synthetic traces
cannot mix with real workspace data. The UI returns the exact local launch command:

```bash
cairn ui --workspace ~/.cairn-demo
```

To return to real data, stop that server and launch the original repository explicitly:

```bash
cairn ui --workspace /path/to/your-repo
```

The same demo is available from the CLI with `cairn demo`. All demo generation is deterministic
and local; it does not download example traces.

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
