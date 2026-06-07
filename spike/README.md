# Phase 0 Spike

Throwaway proof that Cairn's core idea works: a **3-node DAG** (map → reduce → single)
with **content-addressed caching** against a real provider.

Implements §9 action keys (subset: chat steps only), R1 canonical hashing, and a minimal
filesystem AC + CAS (R2 subset). **Not production code** — patterns here migrate into
`cairn/` in Phase 1.

## DAG

```
notes/*.md  ──► [MAP summaries]     ──► outputs/summaries/{stem}.md
                      │
spec.md     ──────────┼──► [REDUCE synthesis] ──► outputs/synthesis.md
                      │            │
                      │            └──► [SINGLE report] ──► outputs/report.md
```

## Run

```bash
# Offline — deterministic mock provider
uv run python -m spike.run spike/demo --mock

# Plan only (cache lookup, no API)
uv run python -m spike.run spike/demo --dry-run

# Live — Ollama Cloud (default model: ollama-cloud/kimi-k2.6:cloud)
export OLLAMA_CLOUD_API_KEY=...
uv run python -m spike.run spike/demo

# Other providers
uv run python -m spike.run spike/demo --provider ollama
uv run python -m spike.run spike/demo --provider openai
```

Secrets are read from the environment only (R3). Ollama Cloud uses host
`https://ollama.com` (OpenAI-compat at `/v1/chat/completions`), matching Lattice.
Optional `OLLAMA_CLOUD_BASE_URL` may be `https://ollama.com` or `https://ollama.com/v1`.
Do not use `https://ollama.com/api` for chat — that path is for native `/api/*` only.
Local Ollama: `OLLAMA_HOST` (default `http://127.0.0.1:11434`). OpenAI: `OPENAI_API_KEY`.

## Prove selective invalidation

```bash
# First build — all nodes run
uv run python -m spike.run spike/demo --mock -v

# Second build — should show all CACHED, 0 tokens
uv run python -m spike.run spike/demo --mock -v

# Edit one note — only that summary + downstream re-run
$EDITOR spike/demo/inputs/notes/alpha.md
uv run python -m spike.run spike/demo --mock -v
```

After editing `alpha.md`, expect only `summaries:alpha`, `synthesis`, and `report` to
re-run — not `summaries:beta` or `summaries:gamma`.

## Tests

```bash
uv run pytest spike/tests -q
```
