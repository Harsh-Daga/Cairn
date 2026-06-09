# Getting started

This guide takes you from zero to a rendered HTML report in a few minutes.

## Install

**Recommended** — one command (macOS, Linux, WSL2):

```bash
curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash
```

Verify:

```bash
cairn --version
```

Ensure `~/.local/bin` is on your `PATH` if the shell cannot find `cairn`.

### Install from source

For development or when you need an editable checkout:

```bash
git clone https://github.com/Harsh-Daga/Cairn.git
cd Cairn
uv sync --group dev
uv pip install -e .
uv run cairn --version
```

---

## Tutorial 1: Provider workflow

Create a project, run an offline build, and open the report.

### 1. Scaffold

```bash
cairn init my-project
cd my-project
cairn validate
```

`cairn init` creates `cairn.toml`, prompt templates, and sample inputs under `inputs/`.

### 2. Preflight (optional)

```bash
export OLLAMA_CLOUD_API_KEY=your-key   # if using default ollama-cloud model
cairn doctor
```

`doctor` checks credentials and model compatibility without spending tokens.

### 3. Build

```bash
cairn status
cairn build --yes --provider-mode recorded
```

`recorded` replays fixtures — no API keys required. Use `--provider-mode live` for real LLM
calls once credentials are set.

### 4. Render

```bash
cairn render -o outputs/bundle --zip
open outputs/bundle/index.html        # macOS
xdg-open outputs/bundle/index.html    # Linux
```

You get a self-contained HTML report with execution graph, step outputs, and metadata.

### 5. Inspect as JSON

```bash
cairn report --json
cairn runs
```

---

## Tutorial 2: Agent capture

Record what a coding agent did in an existing repository.

### 1. Ingest

From your project root (no `cairn init` required):

```bash
cairn ingest --source claude-code
```

Other sources: `codex`, `cursor`, `hermes`, `aider`, `openhands`, `goose`, or `all`.

### 2. List and inspect

```bash
cairn sessions list
cairn show <session_id>
cairn graph <session_id> --kind execution
```

### 3. Render capture bundle

```bash
cairn render --session <session_id> -o outputs/capture-bundle
cairn report --session <session_id> --json
```

Capture and provider reports share the same bundle format.

---

## Tutorial 3: Live workspace

Watch a session update in the browser:

```bash
cairn live serve --session <session_id> --port 8787
```

Open `http://127.0.0.1:8787/session/<session_id>`. The page subscribes to SSE for live events.

---

## Tutorial 4: Snapshots and sharing

```bash
cairn snapshot create --label baseline
cairn snapshot list
cairn collab export /tmp/sync-bundle
cairn render -o outputs/share --zip
```

Encrypt before sharing externally:

```bash
export CAIRN_ENCRYPTION_KEY="your-passphrase"
cairn security encrypt outputs/share.zip outputs/share.zip.enc
```

---

## Tutorial 5: Python SDK

```python
import cairn
from cairn.workflow import run as workflow_run
from cairn.render import html, report_json

project = cairn.Project.open(".")
run = workflow_run(project=project, yes=True, provider_mode="recorded")
print(report_json(run))
html(run, output=project.root / "outputs" / "sdk-bundle")
```

See [Python SDK](sdk.md) for capture ingest and `Run` construction.

---

## Tutorial 6: HTTP API

```bash
export CAIRN_API_TOKEN=local-dev-token
cairn api serve --port 8790
curl -H "Authorization: Bearer local-dev-token" \
  http://127.0.0.1:8790/v1/openapi.json
```

See [HTTP API](api.md) for routes and examples.

---

## What to read next

| Topic | Guide |
|-------|-------|
| Mental model | [Concepts](concepts.md) |
| All commands | [CLI reference](cli.md) |
| Security | [Security](security.md) |
