# CLI reference

Every Cairn command with flags and copy-paste examples. Run `cairn <cmd> --help` for the
latest flag list.

```bash
cairn help
cairn help --verbose
```

---

## Project

| Command | Description |
|---------|-------------|
| `cairn init [DIR]` | Scaffold `cairn.toml`, prompts, sample inputs |
| `cairn validate [DIR]` | Parse config and step graph |
| `cairn doctor [DIR]` | Preflight credentials and model compatibility (no tokens) |
| `cairn status [DIR]` | Per-node cache state and cost estimate |
| `cairn plan [DIR]` | Execution plan with rendered prompts |

```bash
cairn init my-project && cd my-project
cairn validate
# OK: my-cairn-project v0.1.0
#   sources: 2
#   steps: 3
#   nodes: 5

export OLLAMA_CLOUD_API_KEY=your-key
cairn doctor
# doctor: all checks passed
```

---

## Build and workflows

| Command | Description |
|---------|-------------|
| `cairn build` | Execute the default pipeline from `cairn.toml` |
| `cairn workflow list` | List workflow definitions |
| `cairn workflow validate` | Validate workflow |
| `cairn workflow run` | Execute workflow |
| `cairn workflow history` | List workflow runs |

### `cairn build` flags

| Flag | Description |
|------|-------------|
| `--yes` / `-y` | Skip confirmation prompt |
| `--provider-mode recorded\|live` | Fixture replay vs real API (default: `recorded`) |
| `--refresh SELECTOR` | Force re-run matching step or node id (repeatable) |
| `--dry-run` | Plan only, no execution |
| `--concurrency N` | Parallel nodes (default: 4) |
| `--max-cost N` | Abort if estimated cost exceeds limit |

```bash
cairn build --yes --provider-mode recorded
cairn build --yes --provider-mode live --refresh summaries
cairn build --dry-run
```

**Recorded output:**

```
Run: 1780995065130-be3e6c2ad1783c78
NODE                     STATUS       TOKENS
summaries:alpha          RAN              59
…
hits=0 misses=5 tokens=295
```

**Live output (with `--refresh`):**

```
NODE                     STATUS       TOKENS
summaries:alpha          RAN             824
synthesis                RAN            2989
report                   RAN            2453
hits=0 misses=5 tokens=7541
```

**Cache hit (live without refresh):**

```
summaries:alpha          CACHED            0
hits=5 misses=0 tokens=0
```

```bash
cairn workflow run --yes --provider-mode recorded
cairn workflow history
```

---

## Context and prompts

| Command | Description |
|---------|-------------|
| `cairn context scan` | Index context assets into ledger |
| `cairn context list` | List indexed assets |
| `cairn context show <path>` | Show one asset |
| `cairn prompt sync` | Register prompt versions from `prompts/` |
| `cairn prompt list` | List registered prompts |
| `cairn prompt show <ref>` | Show prompt body and metadata |
| `cairn prompt diff <left> <right>` | Diff two prompt versions |

```bash
cairn context scan
# Indexed 4 context assets.

cairn context list
cairn context show inputs/notes/alpha.md

cairn prompt sync
cairn prompt list
cairn prompt show summarize@v1
cairn prompt diff summarize@v1 summarize@v2
```

---

## Capture

| Command | Description |
|---------|-------------|
| `cairn ingest --source <name>` | Batch-import agent transcripts |
| `cairn sessions list` | List captured sessions |
| `cairn sessions replay <id> -o DIR` | Replay session to bundle |
| `cairn show <session_id>` | Session summary |
| `cairn watch install` | Install Claude/Codex hooks |
| `cairn watch status` | Hook install state |
| `cairn watch uninstall` | Remove hooks |
| `cairn live install` | Hooks + Cursor/Hermes tail watchers |
| `cairn live status` | Live install state |
| `cairn live serve --session ID` | Browser UI + SSE (port 8787) |
| `cairn live uninstall` | Remove live install |

**Sources:** `claude-code`, `codex`, `cursor`, `hermes`, `aider`, `openhands`, `goose`, `all`

```bash
cairn ingest --source claude-code --json
# [{"source": "claude-code", "scanned": 1, "inserted": 1, "skipped": 0}]

cairn sessions list
cairn show sess-redacted-001

cairn live install --source all
cairn live status
cairn live uninstall
```

---

## Observability

| Command | Description |
|---------|-------------|
| `cairn runs` | List provider pipeline runs |
| `cairn render` | Build HTML bundle |
| `cairn report` | Unified JSON report |
| `cairn graph <id> --kind KIND` | Export graph as JSON or DOT |
| `cairn artifact list <session_id>` | Artifact inventory |
| `cairn artifact show <hash>` | One artifact |
| `cairn artifact lineage <hash>` | Lineage edges |
| `cairn diff <session-a> <session-b>` | Compare capture sessions |

### `cairn render` flags

| Flag | Description |
|------|-------------|
| `-o DIR` / `--output DIR` | Output directory |
| `--zip` | Also write a zip archive |
| `--run RUN_ID` | Provider run (default: latest) |
| `--session SESSION_ID` | Capture session |
| `--split` | External JSON data file (needs HTTP server) |

```bash
cairn report --json | head -50
cairn render -o outputs/bundle-recorded --zip
cairn render --session sess-redacted-001 -o outputs/capture-bundle

RUN_ID=$(cairn runs | awk '/^[0-9]/ {print $1; exit}')
cairn report --run "$RUN_ID" --json

cairn graph sess-redacted-001 --kind execution
cairn graph _ --kind dependency
cairn diff sess-redacted-001 sess-redacted-002
```

---

## Sharing

| Command | Description |
|---------|-------------|
| `cairn snapshot create --label TEXT` | Point-in-time snapshot |
| `cairn snapshot list` | List snapshots |
| `cairn snapshot diff <left> <right>` | Compare snapshots |
| `cairn snapshot restore <id>` | Restore ledger state |
| `cairn collab export <dest>` | Export sync bundle |
| `cairn collab import <source>` | Import sync bundle |
| `cairn collab status` | Sync cursor state |

```bash
cairn snapshot create --label e2e-checkpoint
cairn collab export /tmp/cairn-sync-out --generate-token
cairn collab import /tmp/cairn-sync-out --token '<token>'
```

---

## API and security

| Command | Description |
|---------|-------------|
| `cairn api serve` | Local HTTP API (default port 8790) |
| `cairn security audit` | Scan for secrets and misconfig |
| `cairn security encrypt IN OUT` | Encrypt a file |
| `cairn security decrypt IN OUT` | Decrypt a file |

```bash
export CAIRN_API_TOKEN=demo-token
cairn api serve --port 8790

export CAIRN_ENCRYPTION_KEY=demo-passphrase
cairn security encrypt outputs/bundle-live.zip outputs/bundle-live.zip.enc
cairn security decrypt outputs/bundle-live.zip.enc /tmp/restored.zip
```

`encrypt` and `decrypt` operate on files only — no project path argument.

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI |
| `ANTHROPIC_API_KEY` | Anthropic |
| `GEMINI_API_KEY` | Gemini |
| `OPENROUTER_API_KEY` | OpenRouter |
| `OLLAMA_CLOUD_API_KEY` | Ollama Cloud |
| `OLLAMA_HOST` | Local Ollama URL |
| `CAIRN_API_TOKEN` | API bearer auth |
| `CAIRN_ENCRYPTION_KEY` | Bundle encryption passphrase |

See [Configuration](configuration.md) for `cairn.toml` and provider details.

---

## Common recipes

```bash
# New project → offline build → report
cairn init demo && cd demo
cairn validate && cairn build --yes --provider-mode recorded
cairn render -o outputs/bundle --zip

# Live cloud build
export OLLAMA_CLOUD_API_KEY=…
cairn build --yes --provider-mode live --refresh summaries

# Capture existing agent work
cairn ingest --source claude-code
cairn render --session <id> -o outputs/capture-bundle

# Full manual test
# See guides/e2e-testing.md
```
