# Cairn — Build Progress

**Current phase:** Phase 4 — Capture: Codex + live hooks  
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

### Exit criteria

| Criterion | Status |
|---|---|
| `cairn/ingest/parsers/claude_code.py` (R19.3) | Done |
| `ingest/normalizer.py`, `ingest/writer.py`, `ingest/usage.py`, `ingest/project_paths.py` | Done |
| Ledger migration v3: `runs.kind`, `events`, `file_artifacts`, `UNIQUE(source, external_id)` | Done |
| `cairn ingest`, `cairn sessions`, `cairn show` | Done |
| Project slug resolver; git context capture | Done |
| Golden fixture + parser test | Done |
| Ingest twice → one `runs` row (invariant 18) | Done |
| Ingest never touches `action_cache` (invariant 20) | Done |
| `pytest` passes; `mypy --strict` + `ruff` clean | Done |
| **Validation gate (human):** ingest on 3 real projects; sessions match memory | Done (lattice 10, trade-bot 5 subagents) |

### Package layout (additions)

```
cairn/
├── ingest/
│   ├── writer.py              # sole SQLite writer for capture
│   ├── normalizer.py
│   ├── usage.py
│   ├── project_paths.py
│   ├── ingest.py
│   └── parsers/
│       └── claude_code.py
├── ledger/schema.py           # v3 migration
└── cli/
    ├── ingest_cmd.py
    ├── sessions_cmd.py
    └── show_cmd.py
```

### Phase log

| Date | Note |
|---|---|
| 2026-06-07 | Phase 3: Claude Code parser, ledger v3, ingest CLI, golden tests, capture invariants 18 & 20. |
| 2026-06-07 | Phase 3 gate: lattice + trade-bot ingest validated; nested subagent discovery. |

---

## Phase 4 — Capture: Codex + live hooks

**Goal:** Codex parity + real-time file snapshots for Claude and Codex.

### Exit criteria

| Criterion | Status |
|---|---|
| `ingest/parsers/codex.py` (R19.5) | Pending |
| `cairn hook` entrypoint (R19.8) | Pending |
| `cairn watch install\|uninstall\|status` | Pending |
| PreToolUse/PostToolUse file snapshots in CAS | Pending |
| `cairn ingest --source codex` | Pending |
| Codex golden fixture + hook tests | Pending |
| **Validation gate (human):** live Claude + Codex session via hooks | **Pending** |

---

## Upcoming phases (not started)

- **Phase 5** — Cursor + bundle v2 + graph UI (product gate)
- **Phase 6** — Hardening + session diff
- **Phase 7+** — Pipeline iteration, agent nodes, multi-agent, polish
