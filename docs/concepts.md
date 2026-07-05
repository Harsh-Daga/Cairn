# Concepts

## What Cairn measures

Cairn ingests local agent logs into a SQLite store (`.cairn/cairn.db`), normalizes them into **traces** and **spans** (OpenTelemetry-aligned), and computes metrics across five pillars. All read paths go through `server/api/payloads.py`; mutations go through the **action registry** (`server/api/actions.py`) so CLI, UI, and API stay in parity.

## v4 architecture

```
agent logs
    │
    ▼
server/ingest/adapters/  ──►  server/ingest/pipeline.py  ──►  .cairn/cairn.db
                                        │
                                        ▼
                              server/analyze/ (incremental views)
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
            server/improve/      server/api/routers/    server/mcp/
            (detectors,          GET /api/*             stdio tools
             experiments)
                    │
                    ▼
            server/app.py  ──►  ui/ (React, cairn ui)
```

| Layer | Location | Role |
|-------|----------|------|
| Ingest | `server/ingest/` | Adapter discovery, parsing, OTLP receiver, cursor tracking |
| Store | `server/store/` | SQLite schema, repos, migrations — **only** place for SQL |
| Analyze | `server/analyze/` | Incremental views: regions, fingerprint, diagnose, outcomes, usage, waste |
| Improve | `server/improve/` | Insight detectors, proposals, experiments, Thompson bandit |
| API | `server/api/` | FastAPI routers, action handlers, SSE event bus |
| UI | `ui/` | 12-page React dashboard consuming `/api/*` |
| Legacy | `cairn/` | v3 port-only tree; see [legacy-v3.md](legacy-v3.md) |

## Pillar 1 — Context profiling

Each turn's assembled prompt is decomposed into **regions**: system, tool schema, tool results, retrieved files, user, history. The `regions` analyzer flags duplicate blocks, stale tool results, unused tool schemas, and re-billing waste.

## Pillar 2 — Behavioral fingerprinting

Sessions compress into a behavioral vector: tool mix, read:write ratio, exploration vs execution, retry rate, context-fill trajectory, turn count. **AMDM** (Mahalanobis + χ² + per-axis EWMA) detects sudden shocks and gradual drift in the Behavior page and `rule_behavioral_drift` detector.

## Pillar 3 — Outcome-anchored quality

After ingest, Cairn optionally captures git and test signals via the `outcomes` view. The **Agent Quality Score** blends structural, coverage, coherence, and temporal signals. **Lucky pass** sessions (chaotic retries, missing verification) are flagged even when a commit landed.

## Pillar 4 — Measured optimize loop

```
observe (detectors) → diagnose (insights) → propose → apply (human-approved) → measure on holdout → verdict
```

Proposals target `CLAUDE.md`, `AGENTS.md`, `.cursor/rules`. Impact is measured on sessions the proposer never saw. See [Optimize loop](optimize.md).

## Pillar 5 — MCP self-awareness

Agents call Cairn via MCP stdio (`cairn mcp`):

- `cairn_have_i_read`
- `cairn_my_recurring_waste`
- `cairn_project_primer`
- `cairn_session_so_far`
- `cairn_should_i_stop`
- `cairn_project_conventions`

## Waste taxonomy

| Category | Trigger |
|----------|---------|
| `DUPLICATE` | Same content hash re-sent across turns |
| `STALE_TOOL_RESULT` | Tool output never referenced, still in window |
| `UNUSED_TOOL_SCHEMA` | Tool defined but rarely called |
| `REBILLING_WASTE` | Stale results re-billed each turn |
| `CONTEXT_ROT` | Peak context >85% (run level) |
| `BLIND_RETRY` | Same tool+args within ≤2 turns |

## Commands

| Task | CLI | Dashboard |
|------|-----|-----------|
| Sync | `cairn sync` | Settings → Sync now |
| Start UI | `cairn ui` | — |
| Session detail | `cairn show ID` | Sessions → row |
| List traces | `cairn traces ls` | Sessions |
| Context | — | Context page |
| Drift | — | Behavior page |
| Quality | — | Quality page |
| Optimize | `cairn optimize` | Optimize page |
| CI gate | `cairn check` | — |
| Export | `cairn export --trace-id ID` | Settings → Export |

See [CLI reference](reference/cli.md) and [API overview](api.md).
