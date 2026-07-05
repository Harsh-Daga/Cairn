# Ingest adapters

Cairn v4 normalizes agent logs through **adapters** in `server/ingest/adapters/`. Each adapter implements discovery (find log files for the workspace) and parsing (emit a `ParsedSession` with events, tool calls, and usage). The pipeline in `server/ingest/pipeline.py` writes traces and spans to `.cairn/cairn.db`.

Adapter IDs are registered in `server/ingest/registry.py`. Filter sync to one adapter with:

```bash
cairn sync --source <adapter_id>
```

## Adapter reference

| Adapter ID | Agent | Discovery roots | Log format |
|------------|-------|-----------------|------------|
| `claude_code` | Claude Code | `~/.claude/projects/` | `*.jsonl` per project slug |
| `codex` | Codex CLI | `~/.codex/sessions/` | rollout `*.jsonl` |
| `cursor` | Cursor | `~/.cursor/projects/` | agent transcripts; subagent lineage preserved |
| `cline` | Cline | VS Code `globalStorage/saoudrizwan.claude-dev/` | `tasks/*/ui_messages.json` |
| `roo` | Roo Code | VS Code `globalStorage/rooveterinaryinc.roo-cline/` | same Cline-family shape |
| `kilo` | Kilo Code | VS Code `globalStorage/kilocode.kilo-code/` | same Cline-family shape |
| `goose` | Goose | `~/.goose/sessions/` | `*.jsonl` |
| `aider` | Aider | `~/.aider/sessions/` | `*.jsonl` |
| `gemini_cli` | Gemini CLI | `~/.gemini/tmp/`, `~/.config/gemini/` | `*.jsonl`, `*.json` |
| `opencode` | OpenCode | `~/.local/share/opencode/sessions/` (or `$XDG_DATA_HOME`) | `*.jsonl` |
| `hermes` | Hermes | `~/.hermes/sessions/` | `*.json` |
| `openclaw` | OpenClaw | `~/.openclaw/` | `*.jsonl` |

## Generic JSONL parser

`server/ingest/adapters/agent_jsonl.py` handles the shared JSONL event shape used by Aider, Goose, and OpenCode. Each adapter sets its `legacy_source` label for trace metadata.

## Claude Code specifics

- Project slug derived from git root via `server/ingest/project_paths.py`
- Subagent transcripts get distinct external IDs (`#subagent:…`)
- Parser: `server/ingest/adapters/claude_code.py`

## Cursor specifics

- Discovers transcript files under workspace slugs matching the repo
- Parses `state.vscdb` and transcript JSON via `server/ingest/adapters/cursor.py`
- Subagent and best-of-N sessions appear as separate swimlanes in the waterfall

## Cline family

Cline, Roo, and Kilo share `server/ingest/adapters/cline_family.py`. Discovery walks VS Code / Cursor `globalStorage` extension folders on macOS, Linux, and Windows.

## OTLP push ingest

In addition to file adapters, Cairn accepts OpenTelemetry JSON traces at:

```
POST /v1/traces
```

The `OtlpReceiver` in `server/ingest/otlp.py` inserts spans directly — useful for agents that can emit OTLP natively.

## Workspace filtering

Discovery functions filter sessions to the active git workspace where possible (Claude project slug, Codex cwd, Cursor slug, Hermes path matching). Adapters that store logs globally (Hermes, Gemini) use heuristics to associate sessions with the current repo.

## Adding an adapter

1. Implement `FileAdapterBase` in `server/ingest/adapters/`
2. Register the adapter ID in `server/ingest/registry.py` → `ADAPTER_IDS` and `build_adapters()`
3. Add a fixture under `tests/fixtures/ingest/` and a smoke test in `tests/test_ingest_adapters.py`

See [Agent capture guide](guides/agent-capture.md) for troubleshooting missing sessions.
