# Cairn

**Local-first inference workspace for AI agents and LLM workflows.**

Cairn records what your agents and models actually did — prompts, tool calls, artifacts, and
outputs — and turns that into shareable HTML reports with execution graphs. One ledger, one CLI,
works offline.

```bash
curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash
cairn init my-project && cd my-project
cairn build --yes --provider-mode recorded
cairn render -o outputs/bundle --zip
```

Open `outputs/bundle/index.html` in a browser. No server required.

---

## Why Cairn?

Developers mix Claude Code, Cursor, Codex, and direct API calls. Provenance ends up scattered
across JSONL logs, chat exports, and dashboards.

Cairn gives you:

- **Unified capture** — ingest sessions from Claude Code, Cursor, Codex, Hermes, Aider, OpenHands, Goose
- **Versioned workflows** — run repeatable LLM pipelines over your repo with content-addressed caching
- **One report shape** — agent sessions and provider builds render the same bundle format
- **Local by default** — SQLite ledger + content-addressable store under `.cairn/`; no account, no cloud
- **Explainability** — turn cards, tool timelines, artifact inventory, and execution DAGs

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash
```

| Platform | Supported |
|----------|-----------|
| macOS (Intel & Apple Silicon) | ✓ |
| Linux (Ubuntu, Debian, Fedora, Arch, Alpine, …) | ✓ |
| WSL2 | ✓ |
| Native Windows | use WSL2 or [install from source](docs/getting-started.md#install-from-source) |

Requires `curl` (or `wget`) and `git`. Python 3.11+ is installed automatically.

Pin a release: `CAIRN_VERSION=v1.0.0 curl -fsSL … | bash`

---

## Quick start

### Run a workflow on your files

```bash
cairn init my-project && cd my-project
cairn validate
cairn workflow list
cairn build --yes --provider-mode recorded   # offline replay for CI
cairn render -o outputs/bundle --zip
cairn report --json
```

Set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, or `OPENROUTER_API_KEY` for live
provider calls (`--provider-mode live`).

### Capture an agent session

From any git repo where agents have run:

```bash
cairn ingest --source claude-code
cairn sessions list
cairn show <session_id>
cairn render --session <session_id> -o outputs/capture-bundle
cairn live serve --session <session_id>    # http://127.0.0.1:8787
```

`cairn ingest` works without a `cairn.toml`. Hooks and watchers are optional.

---

## What you get

Every run produces:

| Output | Description |
|--------|-------------|
| **HTML bundle** | Self-contained report — open via `file://`, no CDN |
| **Execution graph** | DAG of context → prompts → tools → artifacts |
| **Ledger** | Append-only `.cairn/ledger.db` with full provenance |
| **CAS** | Content-addressed blobs for prompts, outputs, snapshots |

Agent capture and provider builds share the same observability model. You do not need to know
which runtime executed the work to read the report.

---

## CLI overview

```bash
cairn help
```

| Group | What it does |
|-------|----------------|
| **Project** | `init`, `validate`, `doctor`, `status`, `plan` |
| **Workflows** | `context`, `prompt`, `workflow`, `build` |
| **Capture** | `ingest`, `watch`, `sessions`, `show`, `live` |
| **Observability** | `runs`, `render`, `report`, `graph`, `artifact`, `diff` |
| **Sharing** | `snapshot`, `collab` |
| **API** | `api serve` — local HTTP + OpenAPI |
| **Security** | `security audit`, encrypt/decrypt bundles |

See the [CLI reference](docs/cli.md) for details.

---

## Python SDK

```python
import cairn
from cairn.workflow import run as workflow_run
from cairn.render import html, report_json

project = cairn.Project.open(".")
run = workflow_run(project=project, yes=True, provider_mode="recorded")
print(report_json(run)["kind"])
html(run, output=project.root / "outputs" / "bundle")
```

---

## HTTP API

```bash
export CAIRN_API_TOKEN=local-dev-token   # optional bearer auth
cairn api serve --port 8790
```

OpenAPI spec at `http://127.0.0.1:8790/v1/openapi.json`. See [API docs](docs/api.md).

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting started](docs/getting-started.md) | Install → first project → first report |
| [Concepts](docs/concepts.md) | How Cairn thinks about projects, sessions, and lineage |
| [CLI reference](docs/cli.md) | Command groups and common flags |
| [Python SDK](docs/sdk.md) | Programmatic access |
| [HTTP API](docs/api.md) | Routes, auth, examples |
| [Security](docs/security.md) | Credentials, scrubbing, encryption |
| [Contributing](CONTRIBUTING.md) | Development setup and guidelines |

Architecture decisions: [docs/adr/](docs/adr/). Full specification: [docs/spec/charter.md](docs/spec/charter.md).

---

## Development

```bash
git clone https://github.com/Harsh-Daga/Cairn.git && cd Cairn
uv sync --group dev && uv pip install -e .
uv run pytest -q
uv run ruff check cairn tests && uv run mypy cairn
```

---

## License

Apache-2.0. See [LICENSE](LICENSE).
