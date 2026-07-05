# Optimize loop

Cairn closes the loop: **observe → diagnose → propose → apply → measure → verdict**. Instruction-file edits are human-approved and measured on a holdout window the proposer never saw.

Implementation lives in `server/improve/` (detectors, proposals, experiments, bandit).

## 1. Observe — insight detectors

After sync, the improve engine runs modular detectors (`server/improve/detectors/`):

| Detector | What it flags |
|----------|---------------|
| `context-window-pressure` | Sessions approaching context limits |
| `identical-tool-calls` | Repeated read/search with same args |
| `oversize-tool-results` | Tool outputs dominating context |
| `high-file-churn` | Excessive file touches per session |
| `retry-loops-detected` | Blind retry patterns |
| `cache-misuse` | Prompt caching opportunities missed |
| `multi-model-cost-spread` | Cost variance across models |
| `runaway-sessions` | Unusually long or expensive runs |
| `rebilling-waste` | Stale results re-billed each turn |
| `behavioral-drift` | Fingerprint deviation from baseline |
| `quality-regression` | Outcome score drops |
| `unused-tools` | Tool schemas rarely invoked |
| `subagent-heavy` | High subagent fan-out |

Insights appear on the **Insights** page and feed the proposal generator.

## 2. Diagnose — evidence chains

Each insight links to an evidence chain (`GET /api/insights/{id}/evidence`) showing supporting traces and spans. Acknowledge insights to track lifecycle: `new` → `ack` → `fixed` / `regressed`.

## 3. Propose

```bash
cairn optimize              # list proposals (dry run)
cairn optimize --llm        # optional LLM reflector (httpx + API key)
cairn optimize --apply      # apply all pending (prefer UI for selective apply)
```

Or on the **Optimize** page, review experiments in the **Proposed** column.

`optimize_propose` maps open insights to managed blocks targeting `AGENTS.md`, `CLAUDE.md`, or `.cursor/rules`. The deterministic generator lives in `server/improve/proposals.py`; the optional reflector is in `server/improve/reflector.py`.

## 4. Apply

Applying an experiment writes a managed block:

```html
<!-- cairn:managed start block-key -->
…instruction text…
<!-- cairn:managed end -->
```

Backups land in `.cairn/backups/`. Apply via UI (**Apply** button) or:

```bash
cairn action experiment_apply --params-json '{"experiment_id":"…"}'
```

## 5. Measure

New sessions ingested after apply form the **holdout** set. When enough holdout sessions exist (`min_holdout`, default 8), Cairn runs causal measurement:

- `server/improve/stats.py` — clustered effective *n*, CUPED-style effect estimates
- `server/improve/experiments.py` — transitions experiment to `measuring` then `verdict`

Trigger measurement manually with `experiment_measure` or wait for post-sync evaluation.

## 6. Verdict

Experiments land in **Verdict** with:

- Effect estimate (waste ↓, quality ↑, stability)
- `n_effective` (sample size after clustering)
- Gated flag when holdout is too small

Rules that repeatedly fail holdout are candidates for hard prune via Thompson sampling (`server/improve/bandit.py`).

## Revert

```bash
cairn experiments revert EXPERIMENT_ID
```

Or **Revert** on the Optimize page. Restores the target file from `.cairn/backups/`.

## Optional LLM reflector

Set environment variables for the reflector backend:

| Variable | Purpose |
|----------|---------|
| `CAIRN_LLM_BASE_URL` | OpenAI-compatible or Ollama base URL |
| `CAIRN_LLM_MODEL` | Model name |
| `CAIRN_LLM_API_KEY` | API key (or provider-specific `OPENAI_API_KEY`, etc.) |

Without LLM config, Cairn uses templated rewrites from evidence.

## CLI ↔ UI parity

| Step | CLI | UI |
|------|-----|-----|
| Propose | `cairn optimize` | Optimize → Find improvements |
| Apply | `cairn action experiment_apply` | Optimize → Apply |
| Revert | `cairn experiments revert ID` | Optimize → Revert |
| List | `cairn experiments ls` | Optimize board |

See also the [Optimize guide](guides/optimize.md) for legacy v3 config keys still referenced in some flows.
