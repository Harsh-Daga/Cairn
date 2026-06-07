# Cairn — Build Progress

**Current phase:** Phase 2 — Provenance & sharing  
**Charter:** [CHARTER.md](CHARTER.md) v1.2

## Phase 0 — Spike & decide ✅

**Goal:** De-risk the core idea — content-addressed caching over a 3-node DAG.

Exit criteria met (technical); human validation gate still pending.

See git history under `spike/` for deliverables.

---

## Phase 1 — Core build engine ✅

**Goal:** Minimum tool genuinely useful to its author — production `cairn/` package.

All Phase 1 exit criteria met. See git history for details.

---

## Phase 2 — Provenance & sharing

**Goal:** Make a build legible to a stranger — full ledger, `run.json`, self-contained `render` bundle.

### Exit criteria

| Criterion | Status |
|---|---|
| Full R14 ledger schema (`runs`, `nodes`, `tool_calls`, `cas_refs` + AC) | Done |
| Non-destructive `user_version` migration from AC-only db | Done |
| Executor records every build; `cairn build` prints `run_id` | Done |
| `runs/<run_id>.json` git-diffable mirror | Done |
| `cairn render` → self-contained `index.html` (`file://`, no fetch) | Done |
| `cairn render --zip` / `--split` | Done |
| `cairn runs` listing | Done |
| Security scan: no secrets/home paths in bundle | Done |
| Ledger boundary: no influence on action keys/plan | Done |
| Golden tests for `run.json` and bundle JSON | Done |
| ADR 0008 (ledger boundary), ADR 0009 (bundle format) | Done |
| `mypy --strict` + `ruff` clean | Done |
| **Validation gate (human):** hand bundle to 5 people; 2 unprompted installs | **Pending** |

### Package layout (additions)

```
cairn/
├── ledger/        # schema, Ledger, run.json mirror
├── render/        # bundle assembler, HTML inliner, viewer assets
├── cache/         # AC now shares Ledger connection
└── cli/           # render, runs
```

### ADRs

| ADR | Summary |
|-----|---------|
| [0008](docs/adr/0008-ledger-append-only-provenance.md) | Ledger append-only; never cache input |
| [0009](docs/adr/0009-self-contained-bundle.md) | Inline JSON + plain DOM; no framework |

### Phase 2.1 hardening (pre-commit)

| Item | Status |
|---|---|
| Escape HTML-significant chars when inlining JSON (`</script>` safe) | Done |
| Never cache empty/truncated completions (`finish_reason`) | Done |
| `--split` shows actionable message under `file://` | Done |
| Structural no-network test (not substring ban on `https://`) | Done |
| No absolute paths in bundle; secret scan on full `index.html` | Done |
| ADR 0010 (empty-completion policy) | Done |

### Phase log

| Date | Note |
|---|---|
| 2026-06-07 | Phase 2: ledger schema + migration, executor integration, run.json, render bundle, CLI, tests. |
| 2026-06-07 | Phase 2.1: embedding escaper, empty-completion guard, split UX, render security tests. |

---

## Upcoming phases (not started)

- **Phase 3** — Iteration ergonomics (`diff`, selectors, `--refresh`, `--max-cost`, `cache gc`)
- **Phase 4** — Agent nodes & tools
- **Phase 5** — Multi-agent & interop
- **Phase 6** — Polish, docs, community
