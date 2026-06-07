# Cairn — Build Progress

**Current phase:** Phase 5.5 — Capture Report Excellence (next)  
**Charter:** [CHARTER.md](CHARTER.md) v2.0

## Phase 0 — Spike & decide ✅

**Goal:** De-risk the core idea — content-addressed caching over a 3-node DAG.

Exit criteria met (technical); human validation gate still pending.

See git history under `spike/` for deliverables.

---

## Phase 1 — Core build engine ✅

**Goal:** Minimum tool genuinely useful to its author — production `cairn/` package.

All Phase 1 exit criteria met. See git history for details.

---

## Phase 2 — Provenance & sharing ✅

**Goal:** Make a build legible to a stranger — full ledger, `run.json`, self-contained `render` bundle.

All Phase 2 exit criteria met. See git history for details.

---

## Phase 3 — Capture: Claude Code batch ingest ✅

**Goal:** Zero-config value from existing Claude Code JSONL.

All Phase 3 exit criteria met. See git history for details.

---

## Phase 4 — Capture: Codex + live hooks ✅

**Goal:** Codex parity + real-time file snapshots for Claude and Codex.

### Exit criteria

| Criterion | Status |
|---|---|
| `ingest/parsers/codex.py` (R19.5) | Done |
| `cairn hook` entrypoint (R19.8) | Done |
| `cairn watch install\|uninstall\|status` | Done |
| PreToolUse/PostToolUse file snapshots in CAS | Done |
| `cairn ingest --source codex` | Done |
| Codex golden fixture + hook tests | Done |
| `pytest` / `mypy --strict` / `ruff` clean | Done |
| **Validation gate (human):** live Claude + Codex session via hooks | Done |

---

## Phase 5 — Capture: Cursor + Hermes + bundle v2 scaffold ✅

**Goal:** End-to-end capture for all four runtimes + tabbed report shell (data + scaffold UI).

### Exit criteria

| Criterion | Status |
|---|---|
| `ingest/parsers/cursor.py` (R19.7) + subagent linking | Done |
| `ingest/parsers/hermes.py` (R19.11) | Done |
| `graph/session_graph.py` (R19.10) | Done |
| Bundle `cairn_bundle_version: 2` — Files \| Graph \| Timeline | Done |
| `cairn render --session`, `cairn graph` | Done |
| `cairn ingest --source cursor\|hermes\|all` | Done |
| Cursor + Hermes golden + graph + bundle v2 tests | Done |
| `pytest` / `mypy --strict` / `ruff` clean | Done |
| **Technical exit:** ingest → render → `file://` opens with tab scaffold | Done |
| **Product gate (deferred to Phase 5.5):** best report + visualizations | Deferred |

### Package layout (additions)

```
cairn/
├── ingest/parsers/cursor.py
├── ingest/parsers/hermes.py
├── graph/session_graph.py
├── render/capture_bundle.py
└── cli/graph_cmd.py
```

### Phase log

| Date | Note |
|---|---|
| 2026-06-07 | Phase 5: Cursor + Hermes parsers, session graph, capture bundle v2 UI, graph CLI, charter §11.8–§11.9 plan. |

---

## Upcoming phases (charter §16)

- **Phase 5.5** — Capture Report Excellence (bundle v3: visual graph, turns, session IDs, diffs)
- **Phase 6** — Live Capture & Live Report (`cairn live serve`, tail watchers, SSE)
- **Phase 7** — Hardening + session diff + multi-session bundle
- **Phase 8+** — Pipeline iteration, agent nodes, multi-agent, polish
