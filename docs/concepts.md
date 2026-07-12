# Concepts

## Traces and spans

Cairn ingests local agent logs into `.cairn/cairn.db`, normalizing them into **traces** (sessions) and **spans** (turns, tool calls, LLM calls). Parent/child span links model causality; **span links** capture retries and handoffs between agents.

All reads go through `server/api/payloads.py`. All mutations go through the **action registry** (`server/api/actions.py`) so CLI, UI, and API stay in parity.

## Incremental views

Analyzer views in `server/analyze/` recompute incrementally per trace:

| View | Output |
|------|--------|
| `regions` | Context decomposition + waste tags |
| `fingerprint` | Behavioral vector + drift distance |
| `diagnose` | Failure localization, cascade root |
| `outcomes` | Git/test signals + quality score |
| `usage` | Token/cost rollups |

## Evidence and provenance

Detector insights carry **evidence chains** — linked spans, metrics, and fingerprints. UI surfaces provenance chips; exports scrub secrets but keep structure.

## Experiments

The optimize loop runs **experiments**: propose → human apply → measure on holdout → anytime-valid verdict (`improved` / `regressed` / `no_effect` / `inconclusive`).

## Fingerprint and drift

Sessions compress into behavioral vectors (tool mix, read:write ratio, retry rate, context trajectory). **AMDM** combines Mahalanobis distance with per-axis EWMA for shock vs gradual drift alerts.

## Tail risk

Tail analytics estimate worst-case session cost using extreme-value methods — exposed on Overview and via `cairn check` gates (see [ci.md](ci.md)).

## Architecture

```
adapters/OTLP → pipeline → SQLite → views → detectors/experiments
                              ↓
                         FastAPI + SSE → React UI + MCP
```

## Pillar summary

1. **Context profiling** — region waste taxonomy (duplicate, stale tool result, rebilling, context rot).
2. **Behavioral fingerprinting** — drift detection on the Behavior page.
3. **Outcome quality** — git + optional test commands from `~/.config/cairn/config.toml`.
4. **Measured optimize** — holdout verdicts with clustered ESS.
5. **MCP self-awareness** — six stdio tools via `cairn mcp`.
6. **Causal traces** — waterfall blame view, retry/handoff link arcs.
