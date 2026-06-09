# Getting started

From zero to an offline HTML report in five minutes.

## Install

**Recommended** — one command (macOS, Linux, WSL2):

```bash
curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash
cairn --version
```

Add `~/.local/bin` to your `PATH` if the shell cannot find `cairn`.

**PyPI** — [pypi.org/project/cairn-workspace](https://pypi.org/project/cairn-workspace/):

```bash
pip install cairn-workspace
cairn --version
```

For an isolated CLI install (recommended on shared machines):

```bash
pipx install cairn-workspace
```

Or with uv:

```bash
uv tool install cairn-workspace
```

Pin a release: `pip install cairn-workspace==1.1.0`

**From source** (development):

```bash
git clone https://github.com/Harsh-Daga/Cairn.git && cd Cairn
uv sync --group dev && uv pip install -e .
```

---

## Path A: Provider workflow (5 minutes)

Run a versioned LLM pipeline over markdown files in your repo.

### 1. Scaffold

```bash
cairn init my-project
cd my-project
cairn validate
```

`cairn init` creates `cairn.toml`, three prompt templates, and sample inputs under `inputs/`.

### 2. Offline build (no API keys)

```bash
cairn status
cairn plan
cairn build --yes --provider-mode recorded
```

Example output:

```
Run: 1780995065130-be3e6c2ad1783c78

NODE                     STATUS       TOKENS
----------------------------------------------
summaries:alpha          RAN              59
summaries:beta           RAN              59
summaries:gamma          RAN              59
synthesis                RAN              59
report                   RAN              59
----------------------------------------------
hits=0 misses=5 tokens=295
```

`recorded` replays fixtures — zero API cost, ideal for CI.

### 3. Render and open

```bash
cairn render -o outputs/bundle --zip
open outputs/bundle/index.html        # macOS
# xdg-open outputs/bundle/index.html  # Linux
```

You get **Cairn Provenance** — a sidebar of pipeline nodes, per-step prompts, token counts,
and upstream dependency hashes.

### 4. Inspect as JSON

```bash
cairn report --json | head -40
cairn runs
```

---

## Path B: Live provider (Ollama Cloud)

The default `cairn init` model is `ollama-cloud/kimi-k2.6:cloud`. Reasoning models need
adequate `max_tokens` (4096+ recommended).

```bash
export OLLAMA_CLOUD_API_KEY=your-key
cairn doctor
cairn build --yes --provider-mode live --refresh summaries
cairn render -o outputs/bundle-live --zip
```

If a previous recorded build filled the cache, use `--refresh` to force live API calls.
See [Provider workflows](guides/provider-workflows.md) for local Ollama and cache details.

---

## Path C: Agent capture (no cairn.toml)

Record what a coding agent did in an existing repository.

```bash
cd your-git-repo
cairn ingest --source claude-code
cairn sessions list
cairn show <session_id>
cairn render --session <session_id> -o outputs/capture-bundle
open outputs/capture-bundle/index.html
```

You get **Cairn Capture** — Timeline, Graph, and Files tabs for the session.

See [Agent capture](guides/agent-capture.md) for hooks, fixtures, and live serve.

---

## E2E demo corpus

A ready-made test repo with three notes, a spec, and prompts:

```bash
git clone https://github.com/Harsh-Daga/Cairn.git
chmod +x Cairn/examples/e2e-demo/setup.sh

# Local Ollama (default)
Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test

# Ollama Cloud + kimi-k2.6
Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test --provider cloud
```

Full manual test checklist: [E2E testing guide](guides/e2e-testing.md).

---

## What to read next

| Topic | Guide |
|-------|-------|
| Mental model | [Concepts](concepts.md) |
| Every command | [CLI reference](reference/cli.md) |
| `cairn.toml` and providers | [Configuration](reference/configuration.md) |
| Security and sharing | [Security](security.md) |
