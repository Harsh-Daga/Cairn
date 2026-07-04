# Concepts

## What Cairn measures

Cairn ingests local agent logs into a SQLite ledger, normalizes events (prompts, tool calls, tokens, timestamps), and computes metrics across five pillars.

## Pillar 1 — Context profiling

Each turn's assembled prompt is decomposed into regions: system, tool schema, tool results, retrieved files, user, assistant history. Detectors flag duplicate blocks, stale tool results, unused tool schemas, and re-billing waste. The profiler warns at **≥70% context fill**; run-level waste tags `CONTEXT_ROT` at **>85%**.

## Pillar 2 — Behavioral fingerprinting

Sessions compress into a vector: tool mix, read:write ratio, exploration vs execution, retry rate, context-fill trajectory, turn count. **AMDM** (Mahalanobis + χ² + per-axis EWMA) detects sudden shocks and gradual drift.

## Pillar 3 — Outcome-anchored quality

After ingest, Cairn optionally runs git and test commands to score sessions. The **Agent Quality Score** blends structural, coverage, coherence, and temporal signals. **Lucky pass** sessions (chaotic retries, missing verification) are flagged even when a commit landed. Session detail can attribute cost across main vs subagent lanes when lineage is present in agent logs.

## Pillar 4 — Measured optimize loop

```
observe → diagnose → propose → apply (human-approved) → measure on holdout → bandit select/prune
```

Proposals target `CLAUDE.md`, `AGENTS.md`, `.cursor/rules`. Impact is measured on sessions the proposer never saw.

## Pillar 5 — MCP self-awareness

Agents call Cairn via MCP: `cairn_have_i_read`, `cairn_project_primer`, `cairn_my_waste_patterns`, `cairn_replay_last`, `cairn_spend_today`.

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
| Sync | `cairn sync` | Sync button |
| Session detail | `cairn show ID` | Sessions → row |
| Profile | `cairn profile ID` | Context page |
| Drift | `cairn behavior` | Behavior page |
| Quality | `cairn outcomes` | Quality page |
| Optimize | `cairn optimize` | Optimize page |
| CI gate | `cairn check` | Settings → Run check |
| Export | `cairn share ID` | Sessions → Export |

See [CLI reference](reference/cli.md).
