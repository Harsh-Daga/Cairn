# Configuration

## v4 observability (default)

Cairn v4 stores session data in `.cairn/cairn.db` and configures the server via environment
variables (prefix `CAIRN_`). The Typer CLI and Settings UI actions map to the same keys.

| Variable | Default | Purpose |
|----------|---------|---------|
| `CAIRN_HOST` | `127.0.0.1` | HTTP bind address |
| `CAIRN_PORT` | `8787` | HTTP port |
| `CAIRN_TOKEN` | — | Required when binding outside loopback |
| `CAIRN_WORKSPACE_ROOT` | cwd | Active git workspace |
| `CAIRN_LLM_BASE_URL` | — | Optional optimize reflector endpoint |
| `CAIRN_LLM_MODEL` | — | Reflector model name |
| `CAIRN_LLM_API_KEY` | — | Reflector API key |

Set runtime values from the CLI:

```bash
cairn config set outcomes.enabled true
```

Or from the UI via `POST /api/actions/config_set`.

### Project layout (v4)

```
your-repo/
└── .cairn/
    ├── cairn.db          # SQLite store (traces, spans, insights, experiments)
    ├── backups/          # instruction-file backups from optimize apply
    └── watch/            # ingest cursors
```

---

## Pipeline projects (`cairn.toml`)

Some examples and demos use a **pipeline** layout with `cairn.toml`. Credentials are **never**
stored in config — only in environment variables.

## Minimal `cairn.toml`

```toml
[project]
name = "my-cairn-project"
version = "0.1.0"

[defaults]
model = "ollama-cloud/kimi-k2.6:cloud"
params = { temperature = 0.0, max_tokens = 4096 }

[sources.notes]
include = ["inputs/notes/**/*.md"]

[steps.summaries]
prompt = "prompts/summarize.md"
over = "source('notes')"
output = "outputs/summaries/{{ item.stem }}.md"
materialization = "cached"
```

`cairn init` scaffolds a working project with this shape.

## Provider and model strings

Models use the form `provider/model-id`:

| Provider prefix | Example | Credential |
|-----------------|---------|------------|
| `ollama/` | `ollama/llama3.2` | Local: `ollama serve`, `OLLAMA_HOST` |
| `ollama-cloud/` | `ollama-cloud/kimi-k2.6:cloud` | `OLLAMA_CLOUD_API_KEY` |
| `openai/` | `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| `anthropic/` | `anthropic/claude-sonnet-4-6` | `ANTHROPIC_API_KEY` |
| `gemini/` | `gemini/gemini-2.0-flash` | `GEMINI_API_KEY` |
| `openrouter/` | `openrouter/…` | `OPENROUTER_API_KEY` |

Run `cairn doctor` to verify credentials and model compatibility before spending tokens.

### Reasoning models

Models like `kimi-k2.6:cloud` may spend tokens on internal reasoning. If `max_tokens` is too
low, live builds fail with `EmptyCompletionError`. Use **4096+** for cloud reasoning models:

```toml
[defaults]
params = { temperature = 0.2, max_tokens = 4096 }
```

## Provider modes

Set at build time with `--provider-mode`:

| Mode | Behavior |
|------|----------|
| `recorded` | Replay fixtures — default for CI, zero API cost |
| `live` | Call configured providers using environment credentials |

```bash
cairn build --yes --provider-mode recorded
cairn build --yes --provider-mode live
cairn build --yes --provider-mode live --refresh summaries
```

### Cache and refresh

Pipeline steps are cached by **action key** (prompt hash + model + params + upstream outputs).
Switching `recorded` → `live` does not invalidate cache automatically. Use `--refresh`:

```bash
# Refresh all summary nodes (step name matches node step)
cairn build --yes --provider-mode live --refresh summaries

# Or wipe cache entirely
rm -rf .cairn/cache
```

## Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | OpenAI provider |
| `ANTHROPIC_API_KEY` | Anthropic provider |
| `GEMINI_API_KEY` | Google Gemini |
| `OPENROUTER_API_KEY` | OpenRouter |
| `OLLAMA_CLOUD_API_KEY` | Ollama Cloud (`https://ollama.com`) |
| `OLLAMA_HOST` | Local Ollama base URL (default `http://127.0.0.1:11434`) |
| `CAIRN_API_TOKEN` | Bearer auth for `cairn api serve` |
| `CAIRN_ENCRYPTION_KEY` | Passphrase for `security encrypt` / `decrypt` |

## E2E demo setup presets

The demo setup script configures provider and `max_tokens` automatically:

```bash
# Local Ollama + llama3.2, max_tokens=1024
./examples/e2e-demo/setup.sh ~/cairn-e2e-test

# Ollama Cloud + kimi-k2.6, max_tokens=4096
./examples/e2e-demo/setup.sh ~/cairn-e2e-test --provider cloud

# Custom model string
./examples/e2e-demo/setup.sh ~/cairn-e2e-test --model ollama/mistral
```

## Capture-only projects

`cairn ingest` works **without** `cairn.toml`. Capture uses the git repo root and agent
transcript paths under `~/.claude/projects/`, Cursor workspaces, etc.

## Project layout

```
my-project/
├── cairn.toml
├── prompts/
│   ├── summarize.md
│   └── …
├── inputs/
├── outputs/              # pipeline outputs (gitignored by default)
└── .cairn/
    ├── cairn.db          # append-only SQLite (v4 observability store)
    ├── cache/cas/        # content-addressed blobs
    ├── sessions/         # capture session mirrors
    ├── snapshots/        # point-in-time snapshots
    └── watch/            # ingest cursors, hook state
```

See [Concepts](../concepts.md) for how sessions, runs, and caching relate.
