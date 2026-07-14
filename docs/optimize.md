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
| `reread-hotspot` | Repeated reads of unchanged file content (same hash) |
| `retry-loops-detected` | Blind retry patterns |
| `cache-misuse` | Prompt caching opportunities missed |
| `multi-model-cost-spread` | Cost variance across models |
| `runaway-sessions` | Unusually long or expensive runs |
| `rebilling-waste` | Stale results re-billed each turn |
| `behavioral-drift` | Fingerprint deviation from baseline |
| `quality-regression` | Outcome score drops |
| `unused-tools` | Tool schemas rarely invoked |
| `subagent-heavy` | High subagent fan-out |
| `stale-tool-results` | Tool output still in context after last reference |
| `failing-command` | Same command failing ≥3× |
| `error-streak` | ≥4 consecutive tool errors |
| `cost-anomaly` | Session cost > μ+3σ for difficulty bucket |

The registry enforces an action contract before an insight can be persisted. Every detector
must provide either a weekly savings estimate or a specific reason the signal cannot be
priced, plus one structured fix payload:

- `instruction` — a `CLAUDE.md` / `AGENTS.md` rule that can be copied;
- `settings` — a concrete model, cache, or tool configuration change; or
- `manual` — a bounded investigation step when automation would overclaim.

Actionable findings appear in the main **Insights** feed and feed the proposal generator.
Signals such as behavioral drift, quality regression, and cost anomalies identify a change
but do not establish its cause; they are explicitly marked as supporting **Diagnostics**.
Expanding any card shows its fix and a copy-to-clipboard control. A detector with neither a
fix nor an explicit null-savings reason fails contract validation instead of reaching the UI.

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
<!-- cairn:begin sha256=<checksum-of-the-managed-body> -->
## Cairn agent guide
- …instruction text…  <!-- cairn:entry rule/<id> conf=0.8 -->
<!-- cairn:end -->
```

The writer accepts only repository-root `AGENTS.md`, `CLAUDE.md`, and `.cursor/rules`.
It preserves every byte outside the fenced block. Before a successful apply it writes an
experiment-specific backup under `.cairn/backups/`; a previously missing target gets a
missing-file backup marker so revert can remove only the file Cairn created.

The checksum covers the complete managed body. If a user or another tool changes anything
inside that body, the next apply or revert reports a conflict and leaves the file untouched.
Resolve the conflicting block manually instead of asking Cairn to clobber it.

Apply via UI (**Apply** button) or:

```bash
cairn action experiment_apply --params-json '{"experiment_id":"…"}'
```

## 5. Measure

New sessions ingested after apply form the **holdout** set. When enough holdout sessions exist (`min_holdout`, default 8), Cairn runs causal measurement:

- `server/improve/stats.py` — clustered effective *n*, plain difference-in-means estimates,
  and an anytime-valid confidence-sequence boundary
- `server/improve/experiments.py` — transitions experiment to `measuring` then `verdict`

Trigger measurement manually with `experiment_measure` or wait for post-sync evaluation.

Sessions in the before and after windows are independent; Cairn does not pair them by list
position and does not synthesize CUPED covariates. The effect is `mean(after) - mean(before)`.
The confidence-sequence scale is the root-sum-square of the two windows' sample standard
deviations and uses the smaller window size. This is deliberately conservative when window
sizes differ. The stored `test_method` is `difference_in_means+anytime_valid_cs`.

Repeated sessions from the same cluster do not count as independent evidence. Cairn computes
clustered effective sample size before measurement, uses it for the holdout gate, and passes
that same effective *n* into the confidence-sequence radius. The effective value is capped by
the smaller raw window; raw session count is never substituted when producing a verdict.

Before producing a verdict, Cairn compares model distribution, project/task distribution,
spans-per-session buckets, tool-call mix, and ingest parser-version mix between windows. Any
material shift returns `confounded` instead of attributing the change to the rule. The stored
data notes name each triggered guard, including agent/schema-version changes inferred from
parser metadata.

## 6. Verdict

Experiments land in **Verdict** with:

- Effect estimate (waste ↓, quality ↑, stability)
- `n_effective` (sample size after clustering)
- Gated flag when holdout is too small

Rules that repeatedly fail holdout are candidates for hard prune via Thompson sampling (`server/improve/bandit.py`).

## Revert

```bash
cairn optimize revert EXPERIMENT_ID
cairn experiments revert EXPERIMENT_ID
```

Or **Revert** on the Optimize page. Revert selects the backup for that exact experiment and
restores only Cairn's managed block, preserving user edits made elsewhere after apply. The
`cairn experiments revert` spelling remains as a compatibility alias.

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

## Appendix — statistics formulas

Cairn uses **anytime-valid confidence sequences** (CS) on plain holdout mean differences
instead of fixed-*z* sequential tests. Sessions in different windows are not paired.

### Difference in means

Given pre-period outcomes \(X_i\) and post-period outcomes \(Y_i\):

\[
\hat{\delta} = \bar{Y} - \bar{X}, \quad
\sigma = \sqrt{s_X^2 + s_Y^2}, \quad
n = \min(n_{\mathrm{pre}}, n_{\mathrm{post}}, n_{\mathrm{clustered}})
\]

### Anytime-valid CS radius

Mixture variance \(\tau^2 = 1.0\) (default), significance \(\alpha = 0.05\):

\[
r_n = \sigma \sqrt{\frac{2(n\tau^2 + \sigma^2)}{n^2\tau^2}
  \ln\!\left(\frac{\sqrt{n\tau^2 + \sigma^2}}{\alpha\,\sigma}\right)}
\]

Confidence interval: \([\hat{\delta} - r_n,\; \hat{\delta} + r_n]\).

Practical band: \(\delta = 2\%\) of baseline magnitude (minimum absolute floor when baseline is zero).

| Verdict | Rule |
|---------|------|
| `improved` | CI entirely below \(-\delta\) |
| `regressed` | CI entirely above \(+\delta\) |
| `no_effect` | CI contained in \([-\delta, +\delta]\) |
| `inconclusive` | otherwise |

### Clustered effective *n*

\[
n_{\text{eff}} = \frac{n}{1 + (\bar{m} - 1)\rho}, \quad \rho = 0.3 \text{ default}
\]

where \(\bar{m}\) is mean cluster size. Measurement gates on `min_holdout` effective sessions.

### Tail return level (EVT)

For session costs \(x_i\), threshold \(u\) at the 90th percentile, GPD fit on exceedances \(y = x - u\):

\[
\text{return\_level}(n_{\text{future}}) = u + \frac{\sigma}{\xi}\left(n_{\text{future}}^{\xi} - 1\right)
\]

Shape \(\xi\) is clamped to \([-0.5, 0.9]\). `cairn check --max-tail-cost X` fails when the projected worst session among the next 1000 exceeds \(X\).

### Power preview

From trailing 14-day traffic:

\[
\text{traces/day} = \frac{\text{count}_{14d}}{14}, \quad
\text{days to verdict} \approx \frac{n_{\text{eff,needed}}}{\text{traces/day}}
\]

Shown as “unknown” when traffic is below 5 traces/week.
