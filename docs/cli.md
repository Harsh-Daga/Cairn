# CLI reference

Install the CLI with the [install script](getting-started.md#install) or `uv tool install`.
Every command supports `--help`.

```bash
cairn help          # command groups
cairn <cmd> --help  # per-command flags
```

## Project

Manage the Cairn project layout and preflight checks.

| Command | Description |
|---------|-------------|
| `cairn init [DIR]` | Scaffold a new project (`cairn.toml`, prompts, sample inputs) |
| `cairn validate` | Check config and step graph; exit non-zero on errors |
| `cairn doctor` | Preflight credentials and model compatibility (no tokens spent) |
| `cairn status` | Show cache/build status for pipeline steps |
| `cairn plan` | Dry-run plan of what `build` would execute |

## Workflows

Define context, prompts, and execute LLM pipelines.

| Command | Description |
|---------|-------------|
| `cairn context scan` | Index context assets into the ledger |
| `cairn context list` | List indexed assets |
| `cairn context show <id>` | Show one asset |
| `cairn prompt sync` | Sync versioned prompts from `prompts/` into CAS |
| `cairn prompt list` | List registered prompts |
| `cairn prompt show <name>` | Show prompt metadata and body hash |
| `cairn workflow list` | List workflow definitions |
| `cairn workflow validate` | Validate workflow YAML |
| `cairn workflow run` | Execute a workflow |
| `cairn build` | Run the default pipeline (`--yes` to skip confirm) |

**Provider modes** (flag `--provider-mode`):

| Mode | Behavior |
|------|----------|
| `recorded` | Replay fixtures — default for CI, zero API cost |
| `live` | Call configured providers using environment credentials |

## Capture

Ingest and inspect agent sessions.

| Command | Description |
|---------|-------------|
| `cairn ingest --source <name>` | Batch ingest transcripts |
| `cairn watch install` | Install capture hooks (Claude Code, Codex) |
| `cairn watch status` | Show hook install state |
| `cairn hook --event <name>` | Hook handler (installed by `watch`) |
| `cairn sessions list` | List captured sessions |
| `cairn sessions replay` | Replay session events |
| `cairn show <session_id>` | Session summary |
| `cairn live serve` | Local HTML workspace + SSE |

**Ingest sources:** `claude-code`, `codex`, `cursor`, `hermes`, `aider`, `openhands`, `goose`, `all`.

Incremental ingest uses `.cairn/watch/cursors.json` to skip unchanged files.

## Observability

Reports, graphs, and run history.

| Command | Description |
|---------|-------------|
| `cairn runs` | List provider runs |
| `cairn render` | Build HTML bundle (`-o DIR`, `--zip`, `--session ID`) |
| `cairn report` | Unified JSON report (`--session ID` for capture) |
| `cairn graph <id> --kind <kind>` | Print execution / artifact / dependency graph |
| `cairn artifact list <session_id>` | Artifact inventory for a session |
| `cairn diff` | Diff snapshots or sessions |

## Sharing

| Command | Description |
|---------|-------------|
| `cairn snapshot create` | Point-in-time project snapshot |
| `cairn snapshot list` | List snapshots |
| `cairn snapshot diff` | Compare snapshots |
| `cairn snapshot restore` | Restore from snapshot |
| `cairn collab export <path>` | Export sync bundle |
| `cairn collab import <path>` | Import sync bundle |
| `cairn collab status` | Collaboration cursor state |

## API & security

| Command | Description |
|---------|-------------|
| `cairn api serve` | Local HTTP API (default port 8790) |
| `cairn security audit` | Scan config and mirrors for secrets |
| `cairn security encrypt` | Encrypt a bundle for sharing |
| `cairn security decrypt` | Decrypt a bundle |

## Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI provider |
| `ANTHROPIC_API_KEY` | Anthropic provider |
| `GEMINI_API_KEY` | Google Gemini |
| `OPENROUTER_API_KEY` | OpenRouter |
| `OLLAMA_CLOUD_API_KEY` | Ollama Cloud |
| `CAIRN_API_TOKEN` | Bearer auth for `cairn api serve` |
| `CAIRN_ENCRYPTION_KEY` | Passphrase for bundle encrypt/decrypt |

Credentials are read from the environment only — never from `cairn.toml`.

## Common workflows

```bash
# New project → offline build → report
cairn init demo && cd demo
cairn validate && cairn build --yes --provider-mode recorded
cairn render -o outputs/bundle --zip

# Capture existing agent work
cairn ingest --source claude-code
cairn render --session <id> -o outputs/capture-bundle

# Live inspection
cairn live serve --session <id>
```

See [Getting started](getting-started.md) for a full walkthrough.
