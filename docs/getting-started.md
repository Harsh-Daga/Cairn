# Getting started

## Golden path

```bash
cd your-repo
cairn sync          # ingest agent logs into .cairn/cairn.db
cairn ui            # start the web UI at http://127.0.0.1:8787
```

On first run, `cairn ui` opens your browser. The FastAPI server binds to loopback only (`127.0.0.1:8787`) unless you pass `--token` for a non-loopback bind.

Stop the server with `Ctrl+C` in the foreground, or run `cairn stop` if a background instance is running.

## What happens

1. **Detect** — Cairn scans known agent log locations (Claude Code, Codex, Cursor, etc.) via ingest adapters in `server/ingest/adapters/`.
2. **Sync** — Sessions are normalized into OpenTelemetry-aligned traces and spans, written to `.cairn/cairn.db`.
3. **Analyze** — Incremental views in `server/analyze/` compute regions, fingerprints, outcomes, and diagnostics.
4. **Serve** — `server/app.py` exposes read APIs under `/api/*` and serves the React UI from `ui/`.

## First run with no history

If no agent logs are found, the Overview page shows onboarding: run **Sync** from Settings, or use `cairn sync` from the terminal.

## Settings UI

Open **Settings** in the sidebar to configure:

- **Workspace** — root path, session count, token gauge
- **Adapters** — detected sources, stream counts, last ingest time; **Rescan adapters** runs `workspace_scan`
- **Data** — Sync now, export scrubbed bundle, rebuild analyzer views
- **MCP** — install stdio server config for agent self-awareness

Runtime toggles set via Settings actions persist as `CAIRN_*` environment variables for the current server process.

## Manual sync

```bash
cairn sync                        # all detected adapters
cairn sync --source claude_code   # one adapter (see docs/adapters.md)
cairn sync --workspace /path/to/repo
```

Or click **Sync now** in Settings.

## Start the UI separately

```bash
cairn ui                          # default: 127.0.0.1:8787, opens browser
cairn ui --no-open                # skip browser launch
cairn ui --port 9000              # custom port
cairn ui --workspace /path/to/repo
```

## Supported agents

| Agent | Log source |
|-------|------------|
| Claude Code | `~/.claude/projects/…/*.jsonl` |
| Codex CLI | `~/.codex/sessions/…/*.jsonl` |
| Cursor | `~/.cursor/projects/…` transcripts + `state.vscdb` |
| OpenCode | `~/.local/share/opencode/sessions/` |
| Goose | `~/.goose/sessions/` |
| Hermes | `~/.hermes/sessions/*.json` |
| Aider | `~/.aider/sessions/` |
| Gemini CLI | `~/.gemini/tmp/**`, `~/.config/gemini/` |
| Cline / Roo / Kilo | VS Code `globalStorage/…/tasks/*/ui_messages.json` |
| OpenClaw | `~/.openclaw/**` |

See [Ingest adapters](adapters.md) for adapter IDs and parser details.

## Project layout (v4)

```
your-repo/
├── .cairn/
│   ├── cairn.db          # SQLite store (traces, spans, insights, experiments)
│   ├── backups/          # instruction-file backups from optimize apply
│   └── watch/            # ingest cursors
├── server/               # FastAPI app, ingest, analyze, improve, MCP
└── ui/                   # React field-notebook UI (built to server/static/)
```

## Next steps

- [Concepts](concepts.md) — v4 architecture, five pillars, waste taxonomy
- [UI tour](ui-tour.md) — all 12 pages
- [API overview](api.md) — `/api` routes
- [Optimize loop](optimize.md) — propose → apply → measure
- [CLI reference](reference/cli.md)
