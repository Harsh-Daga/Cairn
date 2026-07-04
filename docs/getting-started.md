# Getting started

## Golden path

```bash
cd your-repo
cairn
```

1. Detects installed agents (Claude Code, Codex, Cursor, OpenCode, Goose, Hermes, Aider, Gemini CLI, Cline/Roo/Kilo, OpenClaw)
2. Syncs sessions into `.cairn/cairn.db`
3. Opens `http://127.0.0.1:8787` and backgrounds the server

Stop the dashboard: `cairn stop`  
Keep the server in your terminal: `cairn --foreground` or `cairn -f`

## First run with no history

If no agent logs are found, the dashboard shows onboarding: pick a folder, run sync, or point ingest at a specific agent path via Settings.

## Settings UI

Open **Settings** in the sidebar to configure:

- **Agents** — sources, paths, rescan
- **Outcomes** — `test_command`, `build_command` for quality scoring
- **Optimize** — auto-run, holdout size, reflector backend
- **Budgets** — daily/weekly USD and token caps
- **MCP** — `auto_install` toggle (default on), client preference
- **Data** — ledger path, re-ingest, clear

Changes persist to `~/.config/cairn/config.toml`.

## Manual sync

```bash
cairn sync                  # all detected agents
cairn sync --source cursor  # one agent
```

Or click **Sync** in the dashboard topbar.

## Supported agents

| Agent | Log source |
|-------|------------|
| Claude Code | `~/.claude/projects/…/*.jsonl` |
| Codex CLI | `~/.codex/sessions/…/*.jsonl` |
| Cursor | `state.vscdb` + agent transcripts |
| OpenCode | `~/.local/share/opencode/sessions/` |
| Goose | `~/.local/share/goose/sessions/` |
| Hermes | `~/.hermes/sessions/*.json` |
| Aider | `~/.aider/chat-history/` |
| Gemini CLI | `~/.gemini/tmp/**`, `~/.config/gemini/` |
| Cline / Roo / Kilo | VS Code `globalStorage/…/tasks/*/ui_messages.json` |
| OpenClaw | `~/.openclaw/**` |

## Next steps

- [Concepts](concepts.md) — pillars, waste taxonomy, optimize loop
- [Dashboard guide](guides/dashboard.md)
- [Agent capture](guides/agent-capture.md)
- [CLI reference](reference/cli.md)
