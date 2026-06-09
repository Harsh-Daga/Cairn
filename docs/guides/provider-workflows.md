# Provider workflows

Run versioned LLM pipelines over files in your repository. Cairn tracks every step —
prompts, inputs, outputs, tokens — and renders a **Cairn Provenance** HTML bundle.

## Workflow shape

A typical `cairn.toml` pipeline:

```
sources (notes, spec)
       ↓
steps.summaries  (map over each note)
       ↓
steps.synthesis  (combine summaries + spec)
       ↓
steps.report     (polish to executive report)
```

```bash
cairn validate          # parse config, check graph
cairn status            # per-node cache state
cairn plan              # dry-run with rendered prompts
cairn build --yes --provider-mode recorded
```

## Recorded vs live

### Recorded (CI / offline)

```bash
cairn build --yes --provider-mode recorded
```

Replays fixtures from `cairn/data/fixtures/`. No API keys. Example output:

```
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

### Live (real API)

```bash
export OLLAMA_CLOUD_API_KEY=your-key
cairn doctor
cairn build --yes --provider-mode live --refresh summaries
```

Example live output:

```
NODE                     STATUS       TOKENS
----------------------------------------------
summaries:alpha          RAN             824
summaries:beta           RAN             593
summaries:gamma          RAN             682
synthesis                RAN            2989
report                   RAN            2453
----------------------------------------------
hits=0 misses=5 tokens=7541
```

### Cache hits

If you run live **without** `--refresh` after a recorded build, nodes show `CACHED` with
zero tokens — the action key matches. Always use `--refresh` when switching modes for testing.

## Ollama Cloud (kimi-k2.6)

```bash
# Setup demo with cloud preset
examples/e2e-demo/setup.sh ~/cairn-e2e-test --provider cloud
cd ~/cairn-e2e-test

export OLLAMA_CLOUD_API_KEY=your-key
grep '^model' cairn.toml    # ollama-cloud/kimi-k2.6:cloud
grep max_tokens cairn.toml  # 4096

cairn doctor
cairn build --yes --provider-mode live --refresh summaries
```

**Common error:** `EmptyCompletionError: completion returned empty text` — increase
`max_tokens` to 4096+ for reasoning models.

## Local Ollama

```bash
examples/e2e-demo/setup.sh ~/cairn-e2e-test    # default: ollama/llama3.2

ollama serve
ollama pull llama3.2
export OLLAMA_HOST=http://127.0.0.1:11434

cairn doctor
cairn build --yes --provider-mode live --refresh summaries
```

## Render and inspect

```bash
cairn runs
cairn report --json | head -50
cairn render -o outputs/bundle-live --zip
open outputs/bundle-live/index.html
```

The provenance UI shows:

- Run id, status, total tokens
- Sidebar: `summaries:alpha`, `summaries:beta`, `summaries:gamma`, `synthesis`, `report`
- Per node: model, params, input upstream hashes, system prompt, rendered prompt, output

### Explicit run id (optional)

```bash
RUN_ID=$(cairn runs | awk '/^[0-9]/ {print $1; exit}')
cairn report --run "$RUN_ID" --json
cairn render --run "$RUN_ID" -o outputs/bundle-recorded --zip
```

Omitting `--run` uses the latest run.

## Workflow commands

```bash
cairn workflow list
cairn workflow validate
cairn workflow run --yes --provider-mode recorded
cairn workflow history
```

Note: `cairn build` and `cairn workflow run` both execute the pipeline. Workflow history is
populated by `workflow run`, not `build`.

## Context and prompts

```bash
cairn context scan
cairn context list
cairn context show inputs/notes/alpha.md

cairn prompt sync
cairn prompt list
cairn prompt show summarize@v1
```

## Dependency graph

```bash
cairn graph _ --kind dependency --format json
```

Session id is ignored for `--kind dependency`; the graph comes from `cairn.toml` step wiring.

## Related

- [Configuration](../reference/configuration.md) — `cairn.toml`, providers, env vars
- [CLI reference](../reference/cli.md) — all flags
- [E2E testing](e2e-testing.md) — full manual checklist
