<p align="center">
  <strong>Cairn</strong><br>
  Local-first provenance for AI agents and LLM workflows
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="https://pypi.org/project/cairn-workspace/"><img src="https://img.shields.io/pypi/v/cairn-workspace.svg" alt="PyPI"></a>
</p>

---

**Cairn** records what your coding agents and LLM pipelines actually did — prompts, tool
calls, artifacts, token usage — and turns that into **shareable HTML reports** with
execution graphs. One ledger, one CLI, works offline at `file://`.

```bash
curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash
cairn init my-project && cd my-project
cairn build --yes --provider-mode recorded
cairn render -o outputs/bundle --zip && open outputs/bundle/index.html
```

No server. No account. No CDN.

---

## Why Cairn?

Developers mix Claude Code, Cursor, Codex, and direct API calls. Provenance ends up scattered
across JSONL logs, chat exports, and dashboards.

| Problem | Cairn |
|---------|-------|
| Agent logs are opaque JSONL | Normalized events + timeline + graph UI |
| LLM scripts are not reproducible | Versioned prompts, action-key cache, recorded CI mode |
| Reports need a SaaS account | Self-contained HTML bundles you can attach to a PR |
| Capture ≠ pipeline observability | **One report shape** for both paths |

---

## Two paths, one report

### 1. Provider pipeline — run LLM workflows on your files

Declare steps in `cairn.toml`, run over markdown/code in your repo, cache by content hash.

```bash
cairn validate
cairn workflow list
cairn build --yes --provider-mode recorded   # offline CI replay
cairn build --yes --provider-mode live      # real API calls
cairn report --json
cairn render -o outputs/bundle-live --zip
```

Live build with **Ollama Cloud** (`kimi-k2.6:cloud`):

```bash
export OLLAMA_CLOUD_API_KEY=your-key
cairn doctor
cairn build --yes --provider-mode live --refresh summaries
```

### 2. Agent capture — ingest what agents already did

Works in any git repo. No `cairn.toml` required.

```bash
cairn ingest --source claude-code
cairn sessions list
cairn show sess-redacted-001
cairn render --session sess-redacted-001 -o outputs/capture-bundle
cairn live serve --session sess-redacted-001 --port 8787
```

**Sources:** `claude-code`, `codex`, `cursor`, `hermes`, `aider`, `openhands`, `goose`, `all`.

---

## What you get

Every run produces:

| Output | Description |
|--------|-------------|
| **HTML bundle** | Self-contained report — Timeline, Graph, Files tabs; works at `file://` |
| **Execution graph** | DAG of context → prompts → tools → artifacts |
| **Ledger** | Append-only `.cairn/ledger.db` with full provenance |
| **CAS** | Content-addressed blobs for prompts, outputs, snapshots |
| **JSON report** | Unified schema for provider runs and capture sessions |

Provider builds show per-node prompts, token counts, and upstream hashes. Capture sessions
show turn cards, tool calls, and causal edges.

---

## Install

**Install script** (macOS, Linux, WSL2 — bootstraps Python and uv):

```bash
curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash
```

**PyPI** — [cairn-workspace on PyPI](https://pypi.org/project/cairn-workspace/) (v1.1.0+):

```bash
pip install cairn-workspace
# or isolated CLI install (recommended):
pipx install cairn-workspace
# or:
uv tool install cairn-workspace
```

| Method | Command |
|--------|---------|
| Install script | `curl -fsSL …/install.sh \| bash` |
| pip | `pip install cairn-workspace` |
| pipx | `pipx install cairn-workspace` |
| uv | `uv tool install cairn-workspace` |
| Windows (PowerShell) | `irm …/install.ps1 \| iex` |

Pin a version: `pip install cairn-workspace==1.1.0` or `CAIRN_VERSION=v1.1.0 curl -fsSL … \| bash`

Requires Python 3.11+. The install script also requires `curl` (or `wget`) and `git`.

---

## CLI at a glance

```bash
cairn help
```

| Group | Commands |
|-------|----------|
| **Project** | `init`, `validate`, `doctor`, `status`, `plan` |
| **Workflows** | `context`, `prompt`, `workflow`, `build` |
| **Capture** | `ingest`, `watch`, `sessions`, `show`, `live` |
| **Observability** | `runs`, `render`, `report`, `graph`, `artifact`, `diff` |
| **Sharing** | `snapshot`, `collab` |
| **API & security** | `api serve`, `security audit`, `encrypt` / `decrypt` |

Full reference with copy-paste examples: **[docs/reference/cli.md](docs/reference/cli.md)**

---

## HTTP API

```bash
export CAIRN_API_TOKEN=local-dev-token
cairn api serve --port 8790
curl http://127.0.0.1:8790/v1/openapi.json
```

See [HTTP API](docs/reference/api.md).

---

## Python SDK

```python
import cairn
from cairn.workflow import run as workflow_run
from cairn.render import html, report_json

project = cairn.Project.open(".")
run = workflow_run(project=project, yes=True, provider_mode="recorded")
print(report_json(run)["kind"])  # "provider"
html(run, output=project.root / "outputs" / "sdk-bundle")
```

See [Python SDK](docs/reference/sdk.md).

---

## Documentation

| Guide | Description |
|-------|-------------|
| [Getting started](docs/getting-started.md) | Install → first project → first report |
| [E2E testing](docs/guides/e2e-testing.md) | Manual checklist for every feature |
| [Provider workflows](docs/guides/provider-workflows.md) | Pipelines, caching, live providers |
| [Agent capture](docs/guides/agent-capture.md) | Ingest, hooks, live UI |
| [Collaboration](docs/guides/collaboration.md) | Snapshots, sync, encryption |
| [Concepts](docs/concepts.md) | Mental model: sessions, runs, CAS, bundles |
| [Configuration](docs/reference/configuration.md) | `cairn.toml`, providers, env vars |
| [Security](docs/security.md) | Credentials, scrubbing, encryption |

**Try the demo corpus:** `examples/e2e-demo/setup.sh ~/cairn-e2e-test`

---

## Development

```bash
git clone https://github.com/Harsh-Daga/Cairn.git && cd Cairn
uv sync --group dev && uv pip install -e .
uv run pytest -q
uv run ruff check cairn tests && uv run mypy cairn
```

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

Apache-2.0. See [LICENSE](LICENSE).
