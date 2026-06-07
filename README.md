# Cairn

A build system for LLM computation over a corpus of files — including agentic and
multi-agent workflows. *"dbt for LLM work."* Local-first. Git-native. Zero infrastructure.

See [CHARTER.md](CHARTER.md) for the full specification.

## Status

**Phase 0 — Spike.** A throwaway proof-of-concept lives under `spike/`. Production code
begins in Phase 1.

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
