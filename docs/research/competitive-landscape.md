# Research note: competitive landscape

Status: **research note** — not a product commitment or ranking of third-party tools.

Cairn sits at the intersection of spend dashboards, context profilers, eval platforms, and
OpenTelemetry-style observability for *local coding-agent* sessions. The public README comparison
table is the short form; this note records the differentiation claim Cairn actually tries to earn.

## Adjacent categories

| Category | Typical strength | Gap Cairn targets |
|----------|------------------|-------------------|
| Spend dashboards | Token/cost totals by model/day | Causal session traces, waste taxonomy, measured instruction changes |
| Context profilers | Prompt/context size views | Multi-agent ledger + outcomes/experiments over local logs |
| Eval platforms | Suite-driven scoring | Measurements from real coding-agent sessions without requiring a hosted eval harness |
| Generic OTel | Vendor-neutral spans | Agent-specific analyzers, receipts, and local privacy controls over logs + OTLP |

Examples cited publicly (verify upstream yourself): [ccusage](https://github.com/ryoppippi/ccusage),
[Tokscale](https://github.com/junhoyeo/tokscale),
[ContextLens](https://pypi.org/project/contextlens-profiler/),
[OpenAI Evals](https://github.com/openai/evals),
[OpenTelemetry](https://opentelemetry.io/).

## Differentiation Cairn must keep honest

- Local-first by default (no account, loopback bind, opt-in egress with a ledger).
- Evidence surfaces: verification receipts, regressions (no command execution), supervision risk.
- Improve loop with sample-size / CI honesty rather than vanity “saved $X” claims.
- Resource & privacy shield for disk, storage modes, and circuit breakers.

## Non-claims

- This note does not claim feature parity with any named product.
- Adapter coverage and token accuracy vary; see [ACCURACY.md](../../ACCURACY.md).
- Future community registry ideas remain opt-in and schema-bounded — see [roadmap](../roadmap.md).
