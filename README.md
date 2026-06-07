# Cairn

A build system for LLM computation over a corpus of files — including agentic and
multi-agent workflows. *"dbt for LLM work."* Local-first. Git-native. Zero infrastructure.

See [CHARTER.md](CHARTER.md) for the full specification.

## Status

**Phase 1 — Core build engine.** The `cairn` CLI and package live under `cairn/`. The Phase 0
spike remains under `spike/` for reference.

## Install & run

`uv pip install -e .` installs the `cairn` command into this repo's `.venv/bin/`, which is not
on your shell `PATH` until you activate the venv or invoke it explicitly:

```bash
# Option A — activate the venv (once per terminal)
source .venv/bin/activate
cairn init my-project

# Option B — call the venv binary directly
.venv/bin/cairn init my-project

# Option C — uv run (no activation; recommended from repo root)
uv run cairn init my-project
```

Sync dev dependencies first if you have not already:

```bash
uv sync --group dev
uv pip install -e .
```

## Quickstart (Phase 1)

```bash
uv run cairn init my-project && cd my-project
uv run cairn validate
uv run cairn doctor          # checks credentials for configured models
uv run cairn status
uv run cairn build --yes --provider-mode recorded   # offline replay (CI default)
```

For live inference (Ollama Cloud default in the scaffold), set `OLLAMA_CLOUD_API_KEY` and use
`--provider-mode live`.

## Spike (Phase 0)

```bash
uv sync --group dev --extra spike
uv run python -m spike.run spike/demo --mock
uv run python -m spike.run spike/demo --dry-run
uv run python -m spike.run spike/demo
```

Use `--mock` for offline runs. Use `--dry-run` to plan without API calls. The default
live provider is Ollama Cloud (`OLLAMA_CLOUD_API_KEY`, model `kimi-k2.6:cloud`).

See [spike/README.md](spike/README.md) for details.
