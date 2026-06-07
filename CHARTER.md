# Cairn — Project Charter & Technical Design

> **A local-first provenance recorder and optional build system for coding-agent work.**
> Cairn captures what Claude Code, Codex, and Cursor actually did — prompts, tools, file
> edits — as an inferred causal DAG, and renders a self-contained, offline, shareable report.
> When work becomes repeatable, graduate to a declarative pipeline (`cairn.toml`) with
> content-addressed caching and reproducible builds.

> *"Flight recorder + optional dbt for LLM work."* Local-first. Git-native. Zero infrastructure.
> One binary.

**Status:** Draft v2.0 — agent-first charter (Phases 0–2 complete; Phases 3+ are capture-first)
**License (intended):** Apache-2.0
**Audience:** anyone who wants to build the whole thing from this document alone.

---

## 0. How to read this document

This charter is the single source of truth. It is ordered so you can build top to bottom:

1. **Why** (§1–§3) — the problem, the one core idea, and how we're positioned.
2. **What** (§4–§7) — principles, the domain model, and the on-disk layout.
3. **How** (§8–§12) — architecture, capture integrations (Claude Code / Codex / Cursor),
   the two-level DAG model, CLI, flows, and pipeline-mode build engine.
4. **Build it** (§13–§19) — stack, coding rules, testing, the phase plan, risks, and
   how we know it worked.
5. **Appendix** (§20) — glossary, schema, worked examples.
6. **Part II — Detailed Engineering Reference** (R1–R19) — the no-ambiguity implementation
   spec: exact formats, algorithms, protocols, parsers, hook wiring, and edge cases for every
   component. Build from Part II; let Part I's principles (§4) govern when they conflict.

**Two modes, one product:**

| Mode | Entry point | Primary artifact | When |
|---|---|---|---|
| **Capture** (default) | `cairn ingest` / `cairn watch` | Session provenance bundle | Daily agent work |
| **Pipeline** (optional) | `cairn build` | Build outputs + bundle | Repeatable corpus tasks |

Both modes share: ledger, CAS, trajectory model (R7), and `cairn render`.

If a decision isn't written here, the default is: **do the boring, local, file-based,
reversible thing.**

---

## 1. The Problem (and the evidence behind it)

The dominant way people do serious work with coding agents today is **not** a repo full of
`prompts/*.md`. They open Claude Code, Codex, or Cursor and work directly. The agent reads
files, calls tools, edits code, and produces results — but almost nothing durable is left
behind except git diffs and opaque JSONL logs buried in `~/.claude`, `~/.codex`, or
`~/.cursor`.

That creates recurring pain:

- **No audit trail** — "What prompt produced this change? Which tools ran? What did the agent
  read first?"
- **No shareable explanation** — handing someone a PR without the agent's reasoning is
  incomplete; pasting chat logs is unusable.
- **No causal graph** — you see a file diff, not the chain: read → reason → tool → edit.
- **Ephemeral sessions** — compaction, new chats, and tool churn destroy context; there is no
  portable artifact a stranger can open offline.
- **Repeatability is manual** — when the same 5-step pattern appears across sessions, users
  re-prompt from scratch instead of declaring a pipeline.

**This pain is real and widely felt.** claude-devtools (~3k+ stars) proves people want to
*inspect* Claude Code sessions. Chronicle, Rewind, and agentwatch prove people want *capture*
and replay. Langfuse/Braintrust prove teams want *observability* — but as SaaS. Nobody packages
**local, offline, file-centric, shareable provenance with a causal DAG** across Claude Code,
Codex, and Cursor in one tool.

**The old Cairn thesis (build-system-first) solved a different entry point** — researchers
with `inputs/` and `prompts/` in git. That path remains valuable as **Pipeline mode** (Phases
1–2, built). The new default entry point is **Capture mode**: zero config, ingest what agents
already record, render what matters.

---

## 2. The Core Idea (one paragraph, memorize it)

Agent work is a **directed acyclic graph (DAG)** at two levels. **Micro graph (default):** each
coding-agent session is a sequence of events — user prompts, model turns, tool calls, file
reads/writes — with causal edges. Cairn **infers** this graph from agent transcripts and hooks,
stores it in a local ledger + CAS, and renders a **portable provenance bundle** anyone can
open offline. **Macro graph (optional):** when work is repeatable, declare a `cairn.toml`
pipeline; Cairn runs a content-addressed build DAG (dbt-style) over prompts and files, pinning
realized outputs and trajectories. The bridge: both levels use the same **trajectory model**
(R7), the same ledger, and the same bundle renderer. Capture records what happened; Pipeline
replays what should happen — and Capture can **graduate** into Pipeline when patterns stabilize.

Everything else in Cairn serves capture, rendering, or optional pipeline execution.

---

## 3. Prior Art & Positioning (what we reuse vs. what we build)

Honest map of the neighborhood. **We do not rebuild owned territory.**

| Tool / category | What it nails | Why it isn't Cairn |
|---|---|---|
| **claude-devtools** | Desktop inspection of Claude Code JSONL; search, stats, cost. | Electron app; Claude-only; no portable HTML bundle; no file-centric causal graph; no Codex/Cursor. |
| **Chronicle / Rewind** | Claude Code hooks; SQLite; time-travel restore. | Undo-focused; not shareable provenance; single runtime. |
| **Codex hooks** | Lifecycle hooks; `rollout-*.jsonl` transcripts. | Logging framework; no unified cross-agent ledger or bundle. |
| **Cursor agent-transcripts** | Per-workspace JSONL under `~/.cursor/projects/`. | IDE-internal; fragmented storage; no causal graph product. |
| **Langfuse / Braintrust** | Team cloud traces, evals, dashboards. | SaaS; not local-first; not offline `file://` bundles. |
| **dbt** | `ref()`-driven DAG, incremental builds, lineage. | SQL-only. Cairn **borrows the shape** for Pipeline mode. |
| **promptfoo** | Local eval, content-cached model calls. | Evaluation, not session capture or deliverable builds. |
| **LangGraph / CrewAI** | Agent runtimes, orchestration. | They *run* agents; Cairn *records* and optionally *builds*. |

**What Cairn reuses and never builds:**

- **git** — versioning, blame, PR context. Sessions complement `git log`, not replace it.
- **Claude Code / Codex / Cursor** — the agent runtimes. Cairn does not replace them.
- **Agent transcript formats** — we parse them; we do not fork them.
- **Hooks APIs** — Claude Code hooks, Codex hooks; Cairn installs capture hooks only.
- **Jinja2** — Pipeline-mode prompt templating.
- **MCP / A2A** — Pipeline-mode agent nodes (later phases).

**What Cairn builds (the glue nobody has unified):**

1. **Cross-agent ingest** — parsers + normalizers for Claude Code, Codex, Cursor → one trajectory model.
2. **Micro DAG linker** — causal + data edges from events; file-centric index.
3. **Provenance bundle** — self-contained HTML (`file://`), file-first navigation + graph view.
4. **Optional pipeline engine** — `cairn.toml`, AC, CAS, `cairn build` (Phases 1–2, complete).
5. **Graduation path** — session → suggested pipeline (later).

---

## 4. Design Principles & Ground Rules

These are non-negotiable. Every design decision is checked against them.

1. **Local-first, zero-infra.** No server, no account. Network calls only to model providers
   when **invoking** Pipeline mode — never required for Capture mode.
2. **Capture fails open; build fails loud.** Ingest hooks **must never block** the agent
   (exit 0 always). Pipeline `validate`/`doctor` block spend before tokens.
3. **Provenance is the product.** Every session and build output must be traceable to prompts,
   tools, models, and file snapshots. If we choose between slick output and traceable, choose
   traceable (Principle #10, unchanged).
4. **Do one thing well; compose, don't absorb.** Cairn is not an agent runtime, editor, or
   SaaS. It records and optionally builds.
5. **The DAG is inferred, never hand-maintained** — for Capture (from events) and Pipeline
   (from `ref()`/`source()`).
6. **No lock-in, fully reversible.** Delete Cairn; keep your repo, agent logs, and git history.
7. **Boring technology.** Python, SQLite, SHA-256, vanilla JS, hooks subprocesses.
8. **Zero-config capture.** `cairn ingest` from a git repo should work with no `cairn.toml`.
9. **Taste: value in 5 minutes.** Install → ingest last session → render → open HTML.
10. **CAS is internal infrastructure**, not the user-facing product story. Users care about
    bundles and file lineage, not cache keys.
11. **Prefer a step to an agent** — in Pipeline mode. In Capture mode, agents are the reality;
    Cairn documents them honestly.
12. **Multi-runtime from day one of Capture.** Claude Code, Codex, and Cursor are peers, not
    afterthoughts.

---

## 5. Domain Model (the vocabulary)

Learn these nouns; the whole system is built from them.

### 5.1 Shared

- **Project** — a directory Cairn is scoped to. Typically a git repo root. May or may not
  contain `cairn.toml`.
- **Session** — one continuous agent conversation (Claude `sessionId`, Codex rollout id,
  Cursor transcript id). The Capture-mode unit of work.
- **Event** — one normalized row in the micro DAG: `user_prompt`, `assistant_message`,
  `tool_call`, `tool_result`, `file_snapshot`, `sub_agent`, `session_start`, `session_end`,
  `error`, etc. (R7, R19).
- **Trajectory** — ordered `events[]` for one session or one Pipeline agent node. Stored as
  a CAS blob + normalized SQLite rows.
- **Micro graph** — DAG inferred from session events (causal order + data dependencies).
- **Macro graph** — DAG of Pipeline `steps` from `cairn.toml` (optional).
- **Ledger** — append-only SQLite + per-run/session JSON mirrors.
- **CAS** — content-addressable blob store (file snapshots, large tool args/results,
  trajectory JSON).
- **Provenance bundle** — self-contained static HTML report (`cairn render`).
- **Run** — one `cairn build` (Pipeline) **or** one ingested session (Capture). Distinguished
  by `runs.kind`: `"build"` | `"capture"`.

### 5.2 Capture-specific

- **Source** — agent runtime identifier: `claude-code` | `codex` | `cursor`.
- **External id** — runtime's session id (e.g. Claude `sessionId`, Codex rollout uuid).
- **File artifact** — a repo-relative path touched in a session, with optional
  `before_hash` / `after_hash` from hook snapshots.
- **Ingest** — batch or streaming import from JSONL / hooks → ledger.
- **Watch** — install and manage capture hooks in agent config.

### 5.3 Pipeline-specific (unchanged from v1.2)

- **Source (pipeline)** — input file set declared in `cairn.toml`.
- **Prompt** — Jinja2 template in `prompts/`.
- **Step** — build unit: `chat` | `agent` | `dynamic`.
- **`ref()` / `source()`** — DAG dependency declarations.
- **Action Cache (AC)** — action key → output hash (Pipeline only; never fed by ingest).
- **Map / Reduce** — fan-out / fan-in step patterns.
- **Agent node** — Pipeline step with `kind = "agent"` and MCP/A2A/builtin backend.
- **Manifest** — dynamic step's runtime child work-set.
- **Budget** — hard caps on Pipeline agent nodes.

---

## 6. The Project Format (on-disk layout)

### 6.1 Capture-first layout (default — no `cairn.toml` required)

```
my-repo/                          # any git project you work on with agents
├── src/ ...                      # normal repo files (agents edit these)
└── .cairn/                       # GENERATED — gitignored
    ├── ledger.db                 # sessions + events + build runs + tool_calls
    ├── cache/cas/<aa>/<hash>     # blobs: trajectories, snapshots, tool payloads
    ├── sessions/<session_id>.json  # human-readable session mirror
    └── watch/                    # hook install state, last ingest cursors
```

Optional output location for bundles (committed or gitignored per team preference):

```
outputs/bundle/                   # `cairn render` default
├── index.html
└── assets/
```

### 6.2 Pipeline layout (optional — when work is repeatable)

```
my-pipeline/
├── cairn.toml
├── inputs/
├── prompts/
├── agents/                       # optional agent policies
├── outputs/                      # GENERATED build artifacts
│   └── bundle/
└── .cairn/                       # shared ledger + CAS (both modes use same store)
```

### 6.3 Coexistence rules

- One `.cairn/` per project root. Capture sessions and build runs live in the same
  `ledger.db`, distinguished by `runs.kind`.
- **Invariant (ADR 0008):** ingest events never influence action keys or AC entries.
- `cairn.toml` is optional. `cairn init` scaffolds Pipeline layout; `cairn watch install`
  scaffolds Capture hooks only.

### 6.4 `cairn.toml` (Pipeline mode — unchanged schema, see §20.3)

Pipeline config is identical to v1.2. It is **not** required for Capture.

---

## 7. Worked Examples (end to end)

### 7.1 Capture-first (primary user journey)

1. Developer works in Claude Code on `~/my-repo` (no Cairn awareness).
2. `cairn ingest` scans `~/.claude/projects/-Users-harshdaga-my-repo/*.jsonl` (path slug
   algorithm in R19.2), parses unseen sessions, writes to `my-repo/.cairn/ledger.db`.
3. `cairn sessions` lists: time, source, tools, files touched, tokens, git branch.
4. `cairn render --session <id>` → `outputs/bundle/index.html`.
5. Reviewer opens `file://` HTML offline: **Files** tab shows `src/auth.ts` → timeline of
   prompts/tools/edits; **Graph** tab shows causal DAG; **Timeline** shows total order.
6. `cairn render --zip` → attach to PR.

### 7.2 Live capture (richer file snapshots)

1. `cairn watch install --source claude-code` merges hooks into `.claude/settings.local.json`.
2. `PreToolUse` on `Edit|Write` captures **before** file hash; `PostToolUse` captures **after**.
3. On `Stop`, session is finalized; optional `cairn watch --auto-render`.
4. Same bundle as 7.1, but file diffs are exact CAS snapshots, not inferred from git.

### 7.3 Multi-runtime same repo

1. Morning: Cursor session on `my-repo` → `cairn ingest --source cursor`.
2. Afternoon: Codex session → `cairn ingest --source codex`.
3. `cairn sessions` shows both; `cairn render` can bundle one or `--all-since 1d`.

### 7.4 Pipeline mode (graduation — later phase)

1. User notices repeated pattern across sessions.
2. `cairn init` → edit `cairn.toml` + `prompts/`.
3. `cairn build` → macro DAG, AC, `outputs/`.
4. `cairn render --run <build_run_id>` → build lineage bundle (step DAG view).
5. Capture sessions and build runs coexist in one ledger; renderer picks view by target.

---

## 8. Architecture

### 8.1 Layer diagram (end to end)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ AGENT RUNTIMES (external)                                                │
│  Claude Code          Codex CLI/TUI           Cursor IDE                 │
│  ~/.claude/projects/  ~/.codex/sessions/      ~/.cursor/projects/.../  │
└────────────┬──────────────────┬──────────────────────┬────────────────┘
             │ JSONL (batch)     │ JSONL (batch)         │ JSONL (batch)
             │ Hooks (live)      │ Hooks (live)          │ (hooks: future)
             ▼                   ▼                       ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ cairn/ingest/                                                            │
│  parsers/claude_code.py | codex.py | cursor.py                          │
│  normalizer.py → R7 Trajectory                                          │
│  graph/session_graph.py → micro DAG (nodes + edges)                     │
│  hook_cmd.py ← stdin JSON from agent hooks                              │
└────────────┬────────────────────────────────────────────────────────────┘
             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ ledger/ + cache/cas                                                      │
│  runs (kind=capture|build) | events | file_artifacts | tool_calls       │
└────────────┬────────────────────────────────────────────────────────────┘
             │
     ┌───────┴────────┐
     ▼                ▼
┌─────────────┐  ┌──────────────────────────────────────────────────────┐
│ render/     │  │ PIPELINE (optional) — Phases 1–2 built                 │
│ bundle v2   │  │ loader → graph/builder → plan → executor → providers  │
│ Files|Graph │  │ AC + action keys (never fed by ingest)                 │
│ Timeline    │  └──────────────────────────────────────────────────────┘
└─────────────┘
```

### 8.2 Components

| Component | Capture mode | Pipeline mode |
|---|---|---|
| `ingest/` | **Primary** — parsers, hooks, watch | Unused |
| `ledger/` | sessions, events, file_artifacts | + build runs, nodes, tool_calls |
| `cache/cas.py` | trajectory + snapshot blobs | + step outputs |
| `cache/action_cache.py` | **Unused** | AC lookups |
| `graph/session_graph.py` | Infer micro DAG | Unused |
| `graph/builder.py` | Unused | Macro DAG from `cairn.toml` |
| `plan/` | Unused | action keys, cost |
| `executor/` | Unused | parallel build |
| `providers/` | Observe model from transcripts | Invoke HTTP APIs |
| `render/` | Session bundle v2 | Build bundle v1 (same shell) |
| `cli/` | `ingest`, `watch`, `sessions`, `render` | `build`, `plan`, `status`, … |

### 8.3 Adapter interfaces (stable contracts)

**Provider (Pipeline invoke + Capture observe):**

```python
class Provider(Protocol):                  # model completions — Pipeline only
    name: str
    def complete(self, request: CompletionRequest) -> CompletionResult: ...

class ObservedUsage(TypedDict):            # Capture only — parsed from transcripts
    model: str
    input_tokens: int
    output_tokens: int
    cost: float | None
```

Capture **never** calls `Provider.complete()`. It extracts `ObservedUsage` from transcript
lines via `ingest/usage.py`.

**Agent backends (Pipeline only — Phase 8+):** unchanged `AgentBackend` protocol from v1.2.
External agents (Claude Code, Codex, Cursor) are **not** invoked by Cairn in Capture mode;
they are **observed** via ingest.

### 8.4 Ingest writer (normative)

All ingest paths append to the ledger through one module: `ingest/writer.py`.

```
append_event(session_id, seq, event_type, payload) → None
snapshot_file(session_id, path_rel, op, before_hash?, after_hash?) → None
finish_session(session_id, status, totals) → writes sessions/<id>.json
```

- **Idempotency:** re-ingesting the same `external_id` is a no-op (compare source + external_id).
- **Concurrency:** hook handlers and `cairn ingest` serialize writes via SQLite WAL +
  `BEGIN IMMEDIATE` on session rows.
- **Secrets:** scrub env vars, API keys, and bearer tokens before CAS write (R16).

---

## 9. The Cache-Key Algorithm (Pipeline mode only)

> **Capture mode does not use action keys or the Action Cache.** Ingest writes trajectories
> and snapshots to the ledger/CAS for provenance only (ADR 0008). Everything below applies to
> `cairn build` only.

This is the heart of Pipeline mode. Get it exactly right.

For a node `N`, the **action key** is:

```
action_key(N) = sha256(canonical_json({
    "cairn_key_version": 1,
    "kind":          N.kind,                 # "chat" | "agent" | "dynamic"
    "prompt_hash":   sha256(prompt_or_policy_bytes),
    "prompt_front_matter": normalized_front_matter,
    "model":         N.model,
    "params":        canonical(N.params),
    "tools":         canonical(N.tools),     # agent only: ids+versions+purity, sorted
    "sub_agents":    canonical(N.sub_agents), # agent only
    "budget":        canonical(N.budget),    # agent only
    "rendered_inputs_hash": rendered_inputs_hash(N),
}))
```

`rendered_inputs_hash(N)` is a **Merkle** rollup: `sha256(file_bytes)` for each source
file read; the upstream node's **output/trajectory content hash** for each `ref()`. If an
upstream output changes, every downstream key changes automatically. For a **map** node,
each item gets its own key, so editing one of 20 inputs invalidates exactly one output.

Resolution per node:

```
key = action_key(N)
if key in ActionCache:
    output = CAS[ActionCache[key]]                 # CACHE HIT — no tokens, no tool calls
else:
    result = run(N)                                # chat completion OR agent run — the only spend
    output_hash = sha256(result.bytes)
    CAS[output_hash] = result.bytes                # for agents, this includes the trajectory
    ActionCache[key] = output_hash
    Ledger.record(N, key, output_hash, tokens, cost, trajectory, ...)
```

**Handling non-determinism (the crux), for both completions and agent trajectories:**

- `cached` is **pseudo-hermetic**: the first realization is pinned. Same key ⇒ same bytes
  forever, until an input changes. This gives Bazel-like reproducibility on top of a
  non-deterministic operation, and is what makes an *agent run* replayable.
- `cairn build --refresh <selector>` deletes matching AC entries, forcing re-realization.
- `params.temperature` does **not** change the key. To get N samples, declare `samples = n`,
  which adds a `sample_index` to each node's key.
- For **agent nodes**, the cache key includes the *tool set* (ids + versions) and
  sub-agent definitions — because changing an agent's available tools can change its
  output, so it must invalidate the cache.

**Side-effect safety (agent-specific, see §12.6):** an agent node whose tools are all
`pure` is safe to cache. An agent node with any `effectful` tool may **not** be silently
served from cache; it must be declared `volatile`, or the user must explicitly accept
caching with a loud warning.

**Bridge (future):** `cairn replay --session <id>` may pin a captured trajectory for
Pipeline agent steps — out of scope until Phase 8.

---

## 10. Command Surface (the CLI)

### 10.1 Capture commands (hero path)

| Command | What it does |
|---|---|
| `cairn ingest [--since 7d] [--source claude-code\|codex\|cursor\|all]` | Batch-import agent transcripts for cwd's project. |
| `cairn ingest --watch` | Tail new JSONL files (inotify/polling). |
| `cairn watch install [--source …] [--project PATH]` | Install capture hooks (Claude Code, Codex). |
| `cairn watch uninstall \| status` | Manage hook installation. |
| `cairn sessions [--limit N] [--source …]` | List captured sessions. |
| `cairn show <session_id> [--json]` | Session summary or full trajectory. |
| `cairn graph <session_id> [--format dot\|json]` | Export micro DAG. |
| `cairn render [--session ID\|--run ID] [-o dir] [--zip] [--split]` | **Hero** — offline provenance bundle. |
| `cairn doctor` | Check ingest paths reachable, hooks installed, disk space. |

### 10.2 Pipeline commands (retained — Phases 1–2 built)

| Command | What it does |
|---|---|
| `cairn init [dir]` | Scaffold Pipeline project (`cairn.toml`, prompts, inputs). |
| `cairn validate` | Parse config; resolve macro DAG. No tokens. |
| `cairn status` / `cairn plan` | Cache state + cost estimate. |
| `cairn build [selector]` | Execute pipeline. |
| `cairn runs` | List build runs (`kind=build`). |
| `cairn diff` / `cairn trace` / `cairn cache` | Phase 7+ pipeline ergonomics. |
| `cairn run <prompt>` | One-off completion outside DAG. |

### 10.3 Global flags

`--project PATH` — override project root (default: git root from cwd).
`--json` — machine-readable output where supported.

---

## 11. Key Flows (step by step)

### 11.1 Capture batch ingest (Claude Code)

1. Resolve project root `P` = git root of cwd.
2. Compute Claude project slug: `P.as_posix().replace("/", "-")` with leading `-` →
   e.g. `/Users/harshdaga/cairn` → `-Users-harshdaga-cairn`.
3. Glob `~/.claude/projects/<slug>/*.jsonl`.
4. For each file: read `sessionId` from first line; skip if `(source=claude-code, external_id)` exists.
5. Parse lines (R19.3): build `events[]` in `seq` order; link `parentUuid` chain.
6. For each `tool_use` / `tool_result` pair: insert `tool_calls` row.
7. For `Edit|Write|MultiEdit` tools: extract `file_path` from args; record `file_artifact`.
8. Store trajectory JSON in CAS; insert `runs` row (`kind=capture`).
9. Write `.cairn/sessions/<session_id>.json`.

### 11.2 Capture live hooks (Claude Code)

Hook handler: `cairn hook --event <name>` (installed per R19.4).

| Hook event | Cairn action |
|---|---|
| `SessionStart` | `begin_session(source=claude-code, cwd, git_commit, external_id=sessionId)` |
| `UserPromptSubmit` | `append_event(user_prompt)` — hash + inline if < 64 KiB |
| `PreToolUse` matcher `Edit\|Write\|MultiEdit` | Read file → CAS `before_hash`; `append_event(tool_call, pending)` |
| `PostToolUse` | `append_event(tool_result)`; snapshot `after_hash`; update `file_artifacts` |
| `PostToolUse` matcher `Bash` | `tool_call` with command hash only (no env expansion in bundle) |
| `SubagentStart` / `SubagentStop` | `sub_agent` event; link child session if `sessionId` known |
| `Stop` | `finish_session(status=completed)` |

**Contract:** hook command always `exit 0`. On internal error: log to `~/.cairn/hook-errors.log`, still exit 0.

### 11.3 Capture batch ingest (Codex)

1. Glob `~/.codex/sessions/**/rollout-*.jsonl` (recursive).
2. Filter by `session_meta.payload.cwd` matching project root `P` (prefix match).
3. Parse line types: `session_meta`, `event_msg`, `response_item`, `turn_context` (R19.5).
4. Map `response_item.payload.type=function_call` → `tool_call`; results from following items.
5. Map `apply_patch` / `shell` / MCP tools per R19.5 tool table.
6. `turn_context.payload.model` → session model; accumulate usage from `event_msg` completion events.

### 11.4 Capture live hooks (Codex)

Install into `~/.codex/config.toml` `[hooks]` or project `.codex/config.toml` (R19.6).

| Hook event | Cairn action |
|---|---|
| `SessionStart` | `begin_session(source=codex, …)` — read `session_id`, `cwd` from stdin |
| `UserPromptSubmit` | `append_event(user_prompt)` |
| `PreToolUse` matcher `apply_patch\|Edit\|Write` | `before_hash` snapshot |
| `PostToolUse` | `tool_result` + `after_hash` |
| `Stop` | `finish_session` |

Codex hooks require user trust via `/hooks` or `--dangerously-bypass-hook-trust` for CI.
Cairn documents this in `cairn watch install` output.

### 11.5 Capture batch ingest (Cursor)

1. Compute Cursor project dir: `~/.cursor/projects/<slug>/` where slug mirrors path encoding
   (e.g. `Users-harshdaga-cairn` for `/Users/harshdaga/cairn` — detect both `-Users-…` and
   `Users-…` variants; R19.7).
2. Glob `agent-transcripts/<uuid>/<uuid>.jsonl` and `agent-transcripts/<uuid>/subagents/*.jsonl`.
3. Parse `{role, message}` lines (R19.7). `tool_use` blocks in assistant `content[]`.
4. Parent session links child `subagents/*.jsonl` via `sub_agent` events.
5. **Note:** Cursor does not expose stable PreToolUse hooks in v1; file snapshots are
   **post-hoc** from tool args + optional git diff until Cursor documents hooks.

### 11.6 Render & share (both modes)

1. `cairn render --session <id>` loads session row + events + CAS blobs.
2. Build `graph{nodes,edges}` via `graph/session_graph.py`.
3. Build `files[]` index from `file_artifacts`.
4. Embed JSON in `index.html` (`cairn_bundle_version: 2` for capture).
5. `assets/app.js` renders Files (default) | Graph | Timeline tabs.

### 11.7 Pipeline cold build (unchanged)

`validate` → DAG → Planner → Executor → CAS + Ledger → `outputs/`.

---

## 12. Agent Sources, Graph Model & Multi-Agent Design

### 12.1 Stance (read this first)

**Capture mode implements §12.9 (provenance) first.** Cairn is the **flight recorder** around
Claude Code, Codex, and Cursor — not a replacement. Pipeline mode adds **reproducible builds**
when users graduate. The two-level model (§12.2) is the architectural spine.

### 12.2 The two-level model

| Level | Graph | Default? | How obtained |
|---|---|---|---|
| **Micro** | Session event DAG | **Yes** | Inferred from ingest |
| **Macro** | `cairn.toml` step DAG | Optional | Declared + `ref()` |

**Micro graph edges:**

1. **Temporal:** `seq N → seq N+1`.
2. **Causal:** `tool_call` → `tool_result` (same `tool_use_id`).
3. **Data:** `file_snapshot(read)` → later `tool_call(write)` on same `path_rel`.
4. **Delegation:** `sub_agent` → child session's first event.

**Macro graph:** unchanged from v1.2 — `graph/builder.py`, map/reduce, dynamic manifests.

### 12.3 Claude Code integration (normative)

**Transcript location:**

```
~/.claude/projects/<project_slug>/
  <session_uuid>.jsonl          # primary transcript
  <session_uuid>/               # optional subdir for sidechain assets
```

**Project slug:** absolute cwd with `/` → `-`, e.g. `/Users/harshdaga/cairn` → `-Users-harshdaga-cairn`.

**Line types to parse (R19.3):**

| `type` field | Maps to |
|---|---|
| `user` | `user_prompt` |
| `assistant` | `assistant_message` (+ embedded `tool_use` blocks → `tool_call`) |
| `user` with `tool_result` content | `tool_result` |
| `system` | `error` or skip (subtype `api_error`, etc.) |
| `attachment` | skip or `metadata` (hook noise) |
| `file-history-snapshot` | `file_snapshot` hint |
| `permission-mode`, `queue-operation`, `last-prompt` | skip |

**Fields preserved:** `sessionId`, `uuid`, `parentUuid`, `timestamp`, `cwd`, `gitBranch`,
`version`, `message.model`, `message.usage`, `toolUseResult`.

**Hook install target:** `.claude/settings.local.json` (project-local, gitignored) or
`.claude/settings.json` (committed, team choice). `cairn watch install` writes:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "cairn hook --event SessionStart" }] }],
    "UserPromptSubmit": [{ "hooks": [{ "type": "command", "command": "cairn hook --event UserPromptSubmit" }] }],
    "PreToolUse": [{
      "matcher": "Edit|Write|MultiEdit",
      "hooks": [{ "type": "command", "command": "cairn hook --event PreToolUse" }]
    }],
    "PostToolUse": [{
      "matcher": "Edit|Write|MultiEdit|Bash",
      "hooks": [{ "type": "command", "command": "cairn hook --event PostToolUse" }]
    }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "cairn hook --event Stop" }] }]
  }
}
```

`cairn hook` reads JSON from stdin per [Claude Code hooks reference](https://code.claude.com/docs/en/hooks).

### 12.4 Codex integration (normative)

**Transcript location:**

```
~/.codex/sessions/<YYYY>/<MM>/<DD>/rollout-<ISO-timestamp>-<uuid>.jsonl
```

**Session metadata:** first `session_meta` line:

```json
{
  "type": "session_meta",
  "payload": {
    "id": "<uuid>",
    "cwd": "/abs/path/to/project",
    "originator": "codex-tui",
    "cli_version": "…",
    "model_provider": "openai",
    "source": "cli"
  }
}
```

**Line types (R19.5):**

| `type` | Maps to |
|---|---|
| `session_meta` | `session_start` |
| `turn_context` | model + sandbox metadata on event |
| `event_msg` `task_started` | turn boundary |
| `event_msg` `task_complete` | usage totals |
| `event_msg` `user_message` | `user_prompt` |
| `event_msg` `error` | `error` |
| `response_item` `message` | `assistant_message` |
| `response_item` `function_call` | `tool_call` |
| `response_item` `function_call_output` | `tool_result` |

**Codex tool name mapping:**

| Codex tool | Cairn normalized name | File tracking |
|---|---|---|
| `apply_patch` | `edit` | parse patch paths |
| `shell` / `exec_command` | `bash` | command hash only |
| `read_file` / `list_dir` | `read` | `file_snapshot(read)` |
| `mcp__*` | `mcp:<server>:<tool>` | per tool schema |
| `multi_tool_use.parallel` | fan-out parent | child tool_call events |

**Hook install:** `~/.codex/config.toml` or `<project>/.codex/config.toml`:

```toml
[features]
hooks = true

[[hooks.SessionStart]]
matcher = "startup|resume"
[[hooks.SessionStart.hooks]]
type = "command"
command = "cairn hook --event SessionStart --source codex"

[[hooks.PreToolUse]]
matcher = "apply_patch|Edit|Write"
[[hooks.PreToolUse.hooks]]
type = "command"
command = "cairn hook --event PreToolUse --source codex"

[[hooks.PostToolUse]]
matcher = "apply_patch|Edit|Write|Bash"
[[hooks.PostToolUse.hooks]]
type = "command"
command = "cairn hook --event PostToolUse --source codex"

[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "cairn hook --event UserPromptSubmit --source codex"

[[hooks.Stop]]
[[hooks.Stop.hooks]]
type = "command"
command = "cairn hook --event Stop --source codex"
```

Hook stdin fields used: `session_id`, `transcript_path`, `cwd`, `hook_event_name`, `tool_name`,
`tool_use_id`, `tool_input`, `turn_id`, `model`.

### 12.5 Cursor integration (normative)

**Transcript location (observed layout):**

```
~/.cursor/projects/<workspace_slug>/
  agent-transcripts/
    <session_uuid>/
      <session_uuid>.jsonl       # parent agent transcript
      subagents/
        <subagent_uuid>.jsonl    # child agent transcripts
  agent-tools/                   # tool output blobs (optional enrichment)
  terminals/                     # terminal state snapshots (optional enrichment)
  mcps/                          # MCP descriptors (not parsed in v1)
```

**Workspace slug:** derived from workspace root path. Cairn tries, in order:

1. `Users-<path-with-dashes>` (e.g. `Users-harshdaga-cairn`)
2. `-Users-<path-with-dashes>` (Claude-style, if present)
3. `cairn config` override `[capture.cursor] workspace_slug = "…"`

**Line format:**

```json
{"role":"user","message":{"content":[{"type":"text","text":"…"}]}}
{"role":"assistant","message":{"content":[
  {"type":"text","text":"…"},
  {"type":"tool_use","name":"Read","input":{"path":"…"}}
]}}
```

**Tool mapping:**

| Cursor tool name | Normalized | Notes |
|---|---|---|
| `Read`, `Glob`, `Grep` | `read` / `search` | path from `input.path` or `input.glob_pattern` |
| `Write`, `StrReplace`, `EditNotebook` | `edit` | path + content hash |
| `Shell` | `bash` | command hash only |
| `Delete` | `delete` | path |
| `Task` | `sub_agent` | spawns subagent transcript file |

**Hooks:** Cursor does not document a public hook API equivalent to Claude/Codex as of v2.0.
Capture is **batch ingest only** for Cursor in Phase 5. Phase 6 may add Cursor hooks if/when
documented. File snapshots use post-tool content hashes until PreToolUse is available.

### 12.6 Pipeline agent nodes (deferred — Phase 8+)

v1.2 §12.3–§12.11 remain normative for Pipeline mode: `kind = "agent"`, MCP host, A2A,
dynamic manifests, budgets, side-effect safety. They are **not** the default entry point.

### 12.7 What this is explicitly NOT

Unchanged from v1.2 §12.11: Cairn does not replace agent runtimes, run long-lived agents,
or compete with A2A orchestration DSLs.

---

## 13. Tech Stack & Rationale

| Concern | Choice | Why |
|---|---|---|
| **Language** | Python 3.11+ | Ecosystem, contributor reach, Phases 1–2 already built. |
| **Distribution** | `uv`/`pipx` + PyInstaller binaries | Zero-infra install. |
| **CLI** | Typer + Rich | Typed commands, readable output. |
| **Config** | TOML + Pydantic | Pipeline config; hook install metadata. |
| **Ledger** | SQLite (WAL) | Single-writer ingest + concurrent reads. |
| **CAS** | Filesystem sharded by hash | Large blobs, snapshots. |
| **Renderer** | Static HTML + vanilla JS | Offline `file://`; no build step. |
| **Ingest** | JSONL streaming parsers | Match agent native formats. |
| **Hooks** | Subprocess (`cairn hook`) | Agent-native extension points. |
| **Testing** | pytest + golden fixtures per source | Real transcript fixtures from three runtimes. |

---

## 14. Coding Guidelines & Conventions

```
cairn/
├── cli/           # Typer commands; thin
├── ingest/        # parsers, normalizer, hook_cmd, writer, watch
│   ├── parsers/   # claude_code.py, codex.py, cursor.py
│   └── ...
├── graph/
│   ├── builder.py       # Pipeline macro DAG
│   ├── session_graph.py # Capture micro DAG
│   └── selectors.py
├── model/         # Project, Step, Node, Trajectory, CaptureSession
├── loader/        # Pipeline config + prompts
├── plan/          # Pipeline hashing, cost
├── cache/         # AC + CAS
├── ledger/        # SQLite schema + migrations
├── providers/     # HTTP adapters + observe helpers
├── agents/        # Pipeline agent backends (Phase 8+)
├── executor/      # Pipeline scheduler
├── render/        # bundle v1 (build) + v2 (capture)
└── util/
```

**Rules:** unchanged from v1.2 (pure core, mypy strict, injected dependencies, golden hashes).
**Additional:** ingest parsers are **pure** (bytes/JSON in → events out); only `writer.py` touches SQLite.

---

## 15. Testing & Validation Strategy

**Capture-specific tests (required):**

- **Golden transcript fixtures** — one real (redacted) JSONL per source in `tests/fixtures/ingest/`.
- **Normalizer tests** — fixed input → exact `events[]` sequence.
- **Idempotency** — ingest same file twice → one session row.
- **Hook contract** — `cairn hook` always exits 0; malformed stdin → log, no raise.
- **Graph linker** — tool_call → tool_result → file_write chain produces expected edges.
- **Bundle v2 snapshot** — render output HTML structure stable.

**Pipeline tests:** unchanged (RecordedProvider, property tests, golden action keys).

**Validation gates:** per-phase human gates in §16.

---

## 16. Phase-by-Phase Build Plan

Phases 0–2 are **complete**. Do not reopen unless a regression breaks exit criteria.

### Phase 0 — Spike & decide ✅ COMPLETE
De-risked content-addressed DAG + provider adapter.

### Phase 1 — Core build engine ✅ COMPLETE
`init`/`validate`/`doctor`/`status`/`plan`/`build`; TOML; map+reduce; AC+CAS; HTTP Provider;
R18 provider layer; RecordedProvider; tests.

### Phase 2 — Provenance & sharing ✅ COMPLETE
Ledger (R14 v2); `cairn render`; `--zip`/`--split`; `cairn runs`; build `run.json` mirrors.

---

### Phase 3 — Capture: Claude Code batch ingest (2 weeks)
- **Goal:** zero-config value from existing Claude Code JSONL.
- **Deliverables:**
  - `cairn/ingest/parsers/claude_code.py` (R19.3)
  - `ingest/normalizer.py`, `ingest/writer.py`
  - Ledger migration v3: `runs.kind`, `events`, `file_artifacts`, `sessions` metadata
  - `cairn ingest`, `cairn sessions`, `cairn show`
  - Project slug resolver; git context capture
  - Tests: golden fixture from `~/.claude/projects/.../*.jsonl` (redacted)
- **Exit:** `cairn ingest` in a repo with Claude history → sessions listed; events queryable in SQLite.
- **Validation gate:** *you* run ingest on 3 real projects; sessions match what you remember doing.

### Phase 4 — Capture: Codex + live hooks (2 weeks)
- **Goal:** Codex parity + real-time file snapshots for Claude and Codex.
- **Deliverables:**
  - `ingest/parsers/codex.py` (R19.5)
  - `cairn hook` entrypoint (R19.8)
  - `cairn watch install|uninstall|status` for Claude Code + Codex
  - PreToolUse/PostToolUse file snapshots in CAS
  - `cairn ingest --source codex`
- **Exit:** edit file in Codex session → ingest/hooks → `file_artifacts` has before/after hashes.
- **Validation gate:** one live Claude session + one Codex session captured without manual JSONL copy.

### Phase 5 — Capture: Cursor + bundle v2 (2–3 weeks)
- **Goal:** the differentiator — shareable offline report with file-first + graph UI.
- **Deliverables:**
  - `ingest/parsers/cursor.py` (R19.7); subagent linking
  - `graph/session_graph.py`
  - `render/` bundle `cairn_bundle_version: 2` — Files | Graph | Timeline
  - `cairn render --session`, `cairn graph`
  - `cairn ingest --source cursor|all`
- **Exit:** non-user opens `index.html` via `file://` and traces a file change to prompt + tools.
- **Validation gate:** hand bundle to **5 people**; **2 unprompted** "I'd install this" = signal.
  (This is the real Phase 2 product gate, reframed for agent-first.)

### Phase 6 — Capture hardening + session diff (2 weeks)
- **Goal:** retention and trust.
- **Deliverables:**
  - Secret scrubbing in render (extend R16 tests)
  - `cairn diff --session A B` (files changed between sessions)
  - `cairn ingest --watch` (tail JSONL)
  - `cairn render --zip` polish; large bundle `--split`
  - Enrichment from `agent-tools/` blobs when present (Cursor)
- **Exit:** daily `cairn ingest && cairn render` is < 10 s for typical sessions.
- **Validation gate:** ≥3 external users ingest **weekly**, unprompted.

### Phase 7 — Pipeline iteration ergonomics (2 weeks)
- **Goal:** Pipeline mode daily use (old Phase 3).
- **Deliverables:** `diff`, selectors, `--refresh`, `--max-cost`, `samples = n`, `cairn docs`, `cache gc`.
- **Exit:** edit prompt → status → build → diff is fast.
- **Validation gate:** ≥2 users run Pipeline mode weekly alongside capture.

### Phase 8 — Pipeline agent nodes & MCP (3–4 weeks)
- **Goal:** `kind = "agent"` with builtin loop, MCP host, budgets (old Phase 4).
- **Deliverables:** `agents/builtin.py`, MCP host, `cairn trace`, RecordedAgent, trajectory in build bundle.
- **Exit:** agent node caches/replays; effectful agents never silently cached.
- **Validation gate:** external user runs agent node, shares trajectory bundle.

### Phase 9 — Multi-agent & interop (3–4 weeks)
- **Goal:** dynamic manifests, A2A, orchestrator-worker (old Phase 5).
- **Exit:** unchanged manifest → cached children; plugin backend PR from contributor.

### Phase 10 — Polish, docs, community (ongoing)
- **Goal:** 10-minute quickstart (capture-first docs); bundled binaries; contribution guide.
- **Exit:** newcomer: install → `cairn ingest` → render → open bundle from docs alone.

---

## 17. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Agent vendors change JSONL format | Versioned parsers; `cairn doctor` warns on parse errors; fixtures in CI. |
| Cursor storage fragmentation | Adapter tries multiple slug patterns; config override; ingest-only until hooks exist. |
| Hooks break agent UX | Fail-open (exit 0); `watch status` diagnostics; uninstall restores config backup. |
| "Feature, not a tool" | Lead with bundle (Phase 5 gate); capture works without `cairn.toml`. |
| Pipeline vs capture confusion | CLI help separates modes; docs show capture-first path. |
| Scope creep into agent runtime | §12.7 + §19 unchanged. |

---

## 18. Success Metrics

Stars are vanity. Track:

- **Weekly-active capture users** (`cairn ingest` or watch hooks firing)
- **Bundles shared** (the growth loop)
- **Sessions rendered per user per week**
- Unprompted "I use this to understand what the agent did"
- Pipeline adoption (secondary): repos with `cairn.toml`
- External parser contributions (new agent source adapters)

North star: *would the median agent user be annoyed if Cairn disappeared tomorrow?*

---

## 19. Non-Goals (unchanged core)

- Not an agent runtime or IDE plugin.
- Not a hosted observability SaaS.
- Not crypto-compliance tooling.
- Not marketing CAS/cache to end users.
- Not replacing git.
- Not a GUI app (bundle is read-only HTML).

---

## 20. Appendix

### 20.1 Glossary

*Session* — one agent conversation (capture unit). *Event* — one step in the micro DAG.
*Micro graph* — inferred causal DAG from a session. *Macro graph* — Pipeline step DAG.
*Capture* — ingest mode. *Pipeline* — build mode. *Trajectory* — full event sequence (R7).
*Bundle* — offline HTML provenance report. Other terms unchanged from v1.2.

### 20.2 Template variable binding rules

- In a **map** step: `item` is bound per input file with `.path`, `.name`, `.stem`,
  `.content`; the step runs once per item (each item is its own cache node).
- `source(name)` returns that source set's content (or a list when iterated).
- `ref(step)` returns the upstream output: a single object for single/reduce steps, a list
  for map steps.
- `manifest(name)` (dynamic steps) returns the runtime-emitted child items; each item has an
  `id` plus its declared inputs.
- Project-level `vars` are global. Templates render in a Jinja sandbox; no code execution.

### 20.3 `cairn.toml` schema (informal, Pipeline mode)

```
[project]   name (str, required), version (str)
[vars]      key → value (str/num/bool)
[defaults]  model (str), params (table)
[sources.<name>]  include (list[glob], required), exclude (list[glob])

[steps.<name>]
    # common
    output          (path template, required for non-dynamic)
    model           (str, default = defaults.model)
    params          (table, merged over defaults.params)
    materialization ("cached" | "volatile" | "ephemeral", default "cached")
    samples         (int, default 1)
    tags            (list[str])
    when            (predicate over an upstream output, optional)
    # dependency (exactly one of over / inputs / manifest, except dynamic emitters)
    over            (str: "source('x')" | "ref('y')" | "manifest('z')")   # ⇒ map
    inputs          (list[str: source()/ref()])                          # ⇒ reduce/single
    # kind
    kind            ("chat" | "agent", default "chat")
    prompt          (path; chat steps)
    # agent-only
    policy          (path; agent system prompt/instructions)
    tools           (list[str: "mcp:<server>[:<scope>]@<ver>"])
    effects         ("pure" | "effectful", default "pure")
    sub_agents      (list[agent spec])
    budget          (table: max_tokens, max_iterations, max_seconds)  # required for agents
    backend         ("builtin" | "a2a:<url>" | "cli:<cmd>" | "<runtime>:<entry>")
    # dynamic
    dynamic         (bool, default false)   # this step emits a manifest
    emits           (str; name of the child work-set, when dynamic)
```

`over`, `inputs`, and dynamic `emits` are mutually constrained: `over` ⇒ map (fan-out, incl.
over a `manifest`), `inputs` ⇒ reduce/single (fan-in), `dynamic = true` + `emits` ⇒ an
orchestrator that produces a child work-set. Agent steps **must** declare a `budget`.

### 20.4 The single sentence that defines the project

> **Cairn records what coding agents did, explains it as a causal graph and file-centric
> report you can share offline — and optionally turns repeatable work into a cached,
> reproducible pipeline.**

---

*End of Part I. Part II (R1–R19) follows.*

---
---

# PART II — Detailed Engineering Reference (R1–R19)

> **No-ambiguity implementation spec.** Part I (§1–§20) gives the design, contracts, and
> principles. Part II specifies exact formats, algorithms, protocols, parsers, hook wiring,
> and edge cases so the tool can be built without further design decisions. **If Part I and
> Part II ever conflict, Part I's principles (§4) win — record the conflict as an ADR.**

All identifiers, field names, and file paths below are normative.

## R1. Canonical serialization & hashing

The action key (§9) and every content hash depend on a single canonical encoding. Implement
once in `util/canonical.py`; everything else calls it.

- **Canonical JSON:** UTF-8; object keys sorted lexicographically by code point; no
  insignificant whitespace (`separators=(",", ":")`); strings NFC-normalized; booleans/null
  lowercase; integers as bare integers; **floats normalized to shortest round-trip decimal
  string** (reject `NaN`/`Inf`). Parameters that are floats (e.g. `temperature`) are
  normalized to a canonical decimal string before hashing so `0.0`, `0`, and `0.00` collide.
- **Hash:** `sha256`, lowercase hex, 64 chars. Helper: `h(obj) = sha256(canonical_json(obj))`.
- **Source/file bytes** are hashed **raw** (`sha256(file_bytes)`) — no normalization; content
  is content. Text vs binary is irrelevant to hashing.
- **Cache-key version:** the integer `cairn_key_version` is embedded in every action key
  (§9). Bumping it invalidates all caches globally; do this only on a breaking change to the
  key algorithm, and document it in the changelog and an ADR.
- **Determinism is a test target (Coding Rule #6):** every input to `h()` has a golden-hash
  test pinning the exact digest for fixed inputs.

## R2. Filesystem layout & atomicity

```
.cairn/
├── ledger.db            # SQLite: runs, nodes, action_cache (AC), tool_calls, cas_refs
├── cache/
│   └── cas/<aa>/<sha256>   # CAS blobs, sharded by first 2 hex chars (git-style)
├── sessions/<session_id>.json  # capture session mirror
├── runs/<run_id>.json          # build run mirror
├── watch/install.json          # hook install state
├── watch/cursors.json          # ingest byte offsets
├── config.json          # local, non-committed runtime prefs (concurrency, telemetry)
├── lock                 # advisory build lock (flock)
└── tmp/                 # scratch for atomic writes
```

- **AC lives in SQLite** (`action_cache` table, R14) for queryability; **CAS lives on the
  filesystem** as raw blobs for size. This split is deliberate.
- **Atomic writes (mandatory):** write to `tmp/<uuid>`, `fsync`, then `os.replace()` into the
  final sharded CAS path. A CAS write of an already-present hash is a no-op (idempotent), so
  concurrent writers of identical content are safe. Reads are lock-free.
- **Integrity:** on CAS read, optionally re-hash and compare (cheap, behind a `--verify`
  flag); a mismatch means corruption → treat as a miss and recompute, and warn.
- **Build lock:** acquire `flock` on `.cairn/lock` for the duration of a mutating build so two
  concurrent `cairn build` invocations don't interleave AC writes. Read-only commands
  (`status`, `plan`, `diff`, `render`, `trace`) take a shared lock or none.
- **GC (`cairn cache gc`):** mark-and-sweep. Roots = CAS hashes referenced by the most recent
  `--keep-runs N` runs (default 10) plus anything currently materialized under `outputs/`.
  Sweep unreferenced blobs. AC rows whose `output_hash` is swept are deleted.


- **Capture GC:** trajectory hashes from the last 50 capture sessions are GC roots (default; configurable).

- **Capture mode** does not use action keys or AC; ingest never writes `action_cache` (ADR 0008).

## R3. Configuration, secrets & precedence

- **Precedence (low → high):** built-in defaults → `~/.config/cairn/config.toml` (user) →
  `cairn.toml` `[defaults]`/`[project]` → environment variables → CLI flags.
- **Secrets NEVER appear in `cairn.toml` or any committed file.** Providers and HTTP MCP/A2A
  backends name an **environment variable** holding the credential (e.g.
  `api_key_env = "ANTHROPIC_API_KEY"`); Cairn reads the value at runtime. A `.env` file
  (git-ignored) is supported via a dotenv loader; OS keychain is a later option.
- Action keys contain only the env-var **name**, never its value.
- `validate` checks that required credentials are *present* (non-empty) without printing them.

## R4. Model price table & cost estimation

- Ship `cairn/data/prices.toml`: `model → { input_per_mtok, output_per_mtok, currency }`.
  Overridable in `cairn.toml` `[prices.<model>]` and refreshed each release. Unknown models →
  estimation marked "unpriced" (no hard failure; warn).
- **Pre-run estimate:** for each `new`/`stale` node, `est_in = tokenizer.count(rendered
  prompt/policy + input content)`, `est_out = params.max_tokens`. `cost = est_in·price_in +
  est_out·price_out`. **Agent nodes:** worst case `= budget.max_tokens · price` (upper bound).
  `status`/`plan` show per-node and total; `build` confirms above a configurable threshold and
  enforces `--max-cost` as a hard ceiling (R12).
- **Post-run actuals:** taken from each response's usage and recorded in the ledger (R14).
- Tokenizer: provider-native where available; fallback heuristic `ceil(chars/4)`.

## R5. Provider adapter — full specification

**Normalized message model** (`model/messages.py`):

```
Role        = "system" | "user" | "assistant" | "tool"
ContentBlock = Text{text}
             | ToolUse{id, name, input}        # assistant asks to call a tool
             | ToolResult{tool_use_id, content, is_error}
             | Image{...} | Document{...}       # later phases
Message      = {role, content: list[ContentBlock]}
```

Adapters translate this ↔ provider wire format. `complete()` returns the assistant message,
`usage{input_tokens, output_tokens}`, and the `raw` provider response (stored for audit).

**Built-in adapters (v1):** `anthropic` (Messages API), `openai` (Chat Completions/Responses),
`openai-compatible` (any base-URL-overridable OpenAI-style endpoint), and the OpenAI-compatible
families that just need a base URL + key — including `ollama` (local, native `/api/chat`) and
`ollama-cloud` (hosted, `https://ollama.com`, OpenAI-compat at `/v1`), plus groq, together,
deepseek, mistral, fireworks, openrouter, etc. Selection: explicit `provider` field, else
inferred from the `model` string prefix. Per-provider defaults (base URL, supported models,
context limits, rate-limit header names, prompt-cache mode) come from the **capability registry**
(R18.1); credentials resolve via the **credential resolver** (R18.2); retries use **per-provider
policy tables** (R18.3).

**Auth/transport:** bearer/key from the env var named in config; `base_url` overridable.

**Streaming:** internal streaming is allowed for progress and long outputs, but the **stored
output is the fully-assembled final text** (a single deterministic blob). Build does not
depend on streaming.

**Retry/backoff classification (normative):**

| Condition | Handling |
|---|---|
| `429` rate_limit_error | Honor `retry-after` header as a **floor**. Else jittered exponential backoff: base 1s, factor 2, **full jitter**, cap 30s, max 5 attempts. Inspect `*-ratelimit-*` headers to pre-throttle. |
| `529` overloaded_error | Global overload, **not** your rate limit. Jittered exponential backoff (full jitter mandatory to avoid synchronized retry waves); do **not** count against rate-limit pacing; if a fallback model/provider is configured, fail over after a couple of attempts. |
| `408` / network timeout | Retry with backoff. |
| `5xx` (500/502/503) | Retry with backoff (transient). |
| `4xx` (400/401/403/404) | **Fatal, no retry.** Surface a clear, actionable error (auth/request shape). |
| After max attempts | Node **fails** (executor failure policy, R12). |

**Concurrency & pacing:** a bounded `asyncio` semaphore (default from config) plus an optional
token-bucket limiter honoring configured RPM/TPM. **Coalesce identical in-flight requests by
action key** so duplicate work (e.g. two map items that hash identically) shares one call.


**Capture observe path:** `ingest/usage.py` extracts token counts from Claude `message.usage`, Codex `task_complete` events, and Cursor assistant metadata when present. No `Provider.complete()` call.

## R6. The built-in agent loop — exact algorithm

`agents/builtin.py` implements `AgentBackend` for `backend = "builtin"`.

```
run(task):
  materialize task.inputs into a read-only context (and an output workspace dir if file tools)
  tools = mcp_host.list_tools(task.tools)  +  sub_agent_tools(task.sub_agents)
  messages = [ system(policy + tool/sub-agent usage rules),
               user(goal + input references) ]
  iter = 0; tokens = 0; t0 = now()
  loop:
     enforce_budget(iter, tokens, now()-t0, task.budget)   # raises BudgetExhausted
     resp = provider.complete(model, messages, params, tools=schemas)
     tokens += resp.usage; record message event
     if resp.stop_reason == "tool_use":
         for block in resp.tool_use_blocks:
             record tool_call event
             result = (sub_agent.run(...) if block.name is a sub-agent     # recursive
                       else mcp_host.call(block.name, block.input))        # MCP tools/call
             record tool_result event (store large results as separate CAS blobs)
             append ToolResult(block.id, result) to messages
         iter += 1; continue
     if resp.stop_reason == "end_turn":
         break
  outputs = collect_workspace_files()  or  {default: final_assistant_text}
  return AgentResult(outputs, trajectory, usage)
```

- **Budget breach** (`max_iterations` / cumulative `max_tokens` / `max_seconds`): stop, set
  trajectory `status = "budget_exhausted"`, return partial output, mark the node **degraded**
  (visible in `status`/bundle). Hard caps are mandatory — this is the primary infinite-loop
  defense (§12.10).
- **File output convention:** file-writing tools target a designated output workspace; Cairn
  collects produced/changed files as the node's output (content-addressed). Pure agents with
  no file tools output the final assistant text.
- **Pinning:** the entire trajectory (R7) + outputs are content-addressed and pinned per §9.

## R7. Trajectory data model (canonical JSON) — v2

```
Trajectory = {
  version: 2,
  schema: "cairn-trajectory",
  session_id | node_id,
  source: "claude-code" | "codex" | "cursor" | "builtin" | "a2a" | ...,
  external_id: string | null,
  cwd: string,
  git: { branch, commit, dirty: bool },
  model: string,
  params: object | null,          # Pipeline agent only
  started_at, ended_at,
  status: "completed" | "in_progress" | "budget_exhausted" | "failed",
  usage: { input_tokens, output_tokens, cost },
  events: [ Event, ... ],
  graph: { nodes: [...], edges: [...] }   # optional precomputed for render
}

Event =
  | { type:"session_start", source, cwd, git, seq }
  | { type:"session_end",   status, totals, seq }
  | { type:"user_prompt",   text_hash, text_inline?, prompt_id?, seq }
  | { type:"assistant_message", model, text_hash, text_inline?, usage?, seq }
  | { type:"tool_call",     tool_use_id, name, args_hash, args_inline?, seq }
  | { type:"tool_result",   tool_use_id, result_hash, result_inline?, is_error, duration_ms?, seq }
  | { type:"file_snapshot", path_rel, op:"read"|"write"|"edit", before_hash?, after_hash?, seq }
  | { type:"sub_agent",     parent_tool_use_id, child_session_id, child_source, seq }
  | { type:"error",         message, fatal, status_code?, seq }
  | { type:"budget_check",  ... }           # Pipeline builtin only
  | { type:"message",       role, content }  # legacy Pipeline compat
```

- `seq` is monotonic per session, assigned by `ingest/writer.py`.
- Inline caps: 64 KiB for prompts/tool args in SQLite payload; larger → CAS hash only (R17 #14).
- Trajectory blob stored at `trajectory_hash = sha256(canonical_json(trajectory))`.


- **Pipeline compatibility:** builtin/MCP agent trajectories may emit legacy `message` events; capture uses v2 types above.
- Trajectory hash participates in `ref()` for Pipeline agent nodes.

## R8. MCP integration — exact wiring

- Cairn is an MCP **host**; it instantiates one **client per declared server**. Transports:
  **stdio** (spawn subprocess; credentials via env; **never write logs to stdout** — it
  corrupts the JSON-RPC stream; log to stderr/file) and **Streamable HTTP** (OAuth 2.1 + PKCE;
  bearer from the secret store). All messages are JSON-RPC 2.0.
- **Lifecycle:** `initialize` (Cairn sends its protocol version + capabilities) → server
  responds (version + capabilities) → `notifications/initialized` → `tools/list` → during the
  agent loop, `tools/call`. Capability negotiation is honored for backward compatibility.
  Graceful shutdown at node end.
- **Tool identity in the cache key:** `mcp:<server>:<tool>@<version>` **plus a hash of the
  tool's `input_schema`**, so a changed tool signature invalidates the cache (§9).
- **Purity:** default from MCP annotations (`readOnlyHint` → `pure`; `destructiveHint` or no
  annotation → `effectful`), but **annotations are untrusted** (per spec) — the user's
  per-tool/per-step `effects` in `cairn.toml` is authoritative, and the safe default for
  unknown tools is `effectful`.
- **Security:** no token passthrough; user consent surfaced at `validate`/`plan` (declared
  tools listed; effectful tools require acknowledgement). **`sampling/createMessage` is
  disabled by default** (server-initiated LLM calls break reproducibility and cost control);
  if explicitly enabled, route it through Cairn's provider with budget accounting and record it
  in the trajectory.
- **Primitives:** v1 supports **Tools**. **Resources** may later inject read-only context;
  **Prompts** are out of scope.

## R9. A2A integration — exact wiring

- `backend = "a2a:<base_url>"`. **Discovery:** GET `<base_url>/.well-known/agent-card.json`
  (fallback `/.well-known/agent.json`); validate TLS (1.3+ recommended, verify cert); read
  skills, capabilities (streaming/push), auth requirements, modalities.
- **Invocation:** `message/send` with the goal as a `Message` (role `user`, `Parts`: a
  `TextPart` for the goal + `FilePart`/`DataPart` for inputs). If the response is a `Task` in a
  non-terminal state, **poll `tasks/get`** (or consume the SSE stream if the card advertises
  streaming) until a terminal state (`completed`/`failed`/`canceled`/`rejected`).
- **Capture:** final `Artifact`(s) → node output (Parts → files/text); the status transitions,
  messages, and artifacts → the node's trajectory (the remote agent is opaque; Cairn records
  what is observable).
- **Auth at the HTTP/transport layer** (bearer/OAuth from secrets); identity is **not** placed
  in JSON-RPC payloads. New `contextId` per realization; terminal tasks are non-restartable, so
  a `--refresh` starts a fresh task.
- **Reproducibility caveat (must be surfaced):** the cache key for an A2A node covers
  `base_url` + Agent-Card hash + skill id + goal/inputs, but **not** the remote agent's
  internals. External backends are therefore **trust-pinned** (we pin the realized output), not
  **content-pinned** on the remote side — document this clearly in `trace`/bundle.

## R10. CLI-agent & wrapped-runtime backends

- `backend = "cli:<command-template>"`: materialize declared inputs into a temp **working copy**
  (a `git worktree` when the project is a git repo, else a copied dir); run the command, passing
  the goal via stdin/arg/file per the template; capture **(a)** files created/changed in the
  working copy (diff vs the initial snapshot) as the output, and **(b)** stdout/stderr + any
  transcript file as the trajectory. The working copy is a sandbox; such agents are
  **`effectful` by default** unless they write only to the designated output dir.
- `backend = "<runtime>:<entry>"` (e.g. `langgraph:`, `crewai:`): a thin Python entrypoint
  adapter implementing `AgentBackend` by importing/invoking the runtime and mapping its events
  into the Trajectory model (R7) as faithfully as the runtime exposes them.
- These backends honor the same caching, pinning, budget, and effects rules as `builtin`.

## R11. Dynamic steps — manifest format, child keying, pruning

**Manifest** (emitted by a `dynamic` step, content-addressed and pinned):

```
Manifest = {
  version, emitter_node, emitter_key,
  items: [ { id, inputs: {...}, params?: {...}, prompt_override?, policy_override? }, ... ]
}
```

- **`id` stability rule:** `id` MUST be derived deterministically from item content (e.g.
  `slug(title) + "-" + short_hash(payload)`), so the same logical item keeps the same `id`
  across runs and across manifest reorderings. Cairn validates `id` uniqueness; duplicates are
  a hard error.
- **Child key:** `action_key` over (child prompt/policy, model, params, `item.inputs` hashes).
  Manifest membership/order is **not** in the child key, so an identical recurring item is a
  cache hit even if the manifest reordered.
- **Rebuild diff (by `id`):** new id → run; same id + same payload → cache hit; same id +
  changed payload → stale → run; removed id → **prune** its `outputs/` files (blobs remain in
  CAS until `gc`). `status` reports adds / changes / removes.

## R12. Executor — scheduling, concurrency, failure, resume

- **Scheduling:** topological levels; within a level, run with a bounded `asyncio` semaphore
  (default concurrency from config). A `dynamic` emitter runs, its manifest expands into child
  nodes, and those children join the schedule (a runtime level).
- **Cost ceiling:** before each model/agent call, if projected cumulative cost would exceed
  `--max-cost`, **stop** and report what completed and what remains.
- **Failure policy:** default **fail-fast-per-branch** — a failed node marks its downstream
  `blocked` (skipped) but independent branches continue; the build exits non-zero with a
  summary. `--keep-going` maximizes completed nodes. A failed node writes **no** partial output
  (atomicity, R2).
- **Resume is free:** because every successful node is in the AC, re-running `cairn build` after
  a failure makes completed nodes cache hits and re-runs only failed/`blocked` nodes. No special
  resume state exists — this is the payoff of content-addressing. `result:failed+` (R13) targets
  exactly the previously-failed subgraph.
- **Idempotency guarantee:** same inputs + same cache ⇒ same result (pinned), every run.

## R13. Selector grammar

- **Atoms:** `name` (a step); `tag:<t>`; `state:new` / `state:modified` (computed from the AC —
  `modified` ≡ action key differs from the last recorded key); `result:failed|error|success`
  (from the last run in the ledger).
- **Graph operators:** `+name` (name + all ancestors), `name+` (name + all descendants),
  `+name+` (both), `N+name` / `name+N` (depth-limited); **union** by space-separating;
  subtraction via `--exclude <selector>`.
- Examples: `cairn build state:modified+` (everything changed plus its descendants);
  `cairn build result:failed+` (retry the failed subgraph); `cairn build +synthesis`
  (synthesis and all its upstreams). Parser lives in `graph/selectors.py`.
- **Cairn needs no `--state` manifest babysitting** (unlike dbt's `state:modified`): the Action
  Cache *is* the persistent state, so `state:modified` selection is automatic and exact. An
  optional `--against <run|branch>` may later compare to another ledger for cross-environment
  reuse.


> **Note:** R8–R13 apply to **Pipeline mode** only. Capture mode uses R19 instead of R6/R8–R10 for runtime wiring.

## R14. Ledger — SQLite schema v3

```sql
PRAGMA user_version = 3;

-- Extended runs (capture + build)
CREATE TABLE runs (
  run_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL DEFAULT 'build',  -- 'capture' | 'build'
  source TEXT,                          -- claude-code | codex | cursor | null for build
  external_id TEXT,                     -- agent session id
  cwd TEXT,
  git_branch TEXT,
  git_commit TEXT,
  started_at TEXT NOT NULL,
  ended_at TEXT,
  status TEXT NOT NULL,
  trajectory_hash TEXT,
  total_cost REAL,
  total_input_tokens INTEGER,
  total_output_tokens INTEGER,
  cairn_version TEXT,
  key_version INTEGER,
  UNIQUE(source, external_id)           -- idempotent ingest
);

CREATE TABLE events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  event_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);

CREATE TABLE file_artifacts (
  run_id TEXT NOT NULL,
  path_rel TEXT NOT NULL,
  first_seq INTEGER NOT NULL,
  last_seq INTEGER NOT NULL,
  before_hash TEXT,
  after_hash TEXT,
  PRIMARY KEY (run_id, path_rel, last_seq)
);

-- Build tables (unchanged from v2)
CREATE TABLE nodes (
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  step TEXT NOT NULL,
  item_id TEXT,
  kind TEXT NOT NULL,
  action_key TEXT NOT NULL,
  output_hash TEXT,
  status TEXT NOT NULL,
  model TEXT NOT NULL,
  params_json TEXT NOT NULL,
  input_tokens INTEGER NOT NULL,
  output_tokens INTEGER NOT NULL,
  cost REAL,
  duration_ms INTEGER,
  started_at TEXT NOT NULL,
  ended_at TEXT NOT NULL,
  rendered_prompt TEXT,
  system_prompt TEXT,
  PRIMARY KEY (run_id, node_id)
);

CREATE TABLE tool_calls (
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,   -- build: node_id; capture: run_id used as node_id
  seq INTEGER NOT NULL,
  tool_id TEXT,
  name TEXT,
  args_hash TEXT,
  result_hash TEXT,
  is_error INTEGER,
  duration_ms INTEGER,
  PRIMARY KEY (run_id, node_id, seq)
);

CREATE TABLE action_cache (
  action_key TEXT PRIMARY KEY,
  output_hash TEXT NOT NULL,
  kind TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_used_at TEXT NOT NULL,
  model TEXT
);

CREATE TABLE cas_refs (
  output_hash TEXT NOT NULL,
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  PRIMARY KEY (output_hash, run_id, node_id)
);
```

- **`sessions/<session_id>.json`** and **`runs/<run_id>.json`** are human-readable mirrors for
  git-diffable provenance and as render inputs.
- **Migrations:** keyed on `PRAGMA user_version`; applied on open; never destructive.
- Migration v2→v3: add `runs.kind`, `source`, `external_id`, `cwd`, `trajectory_hash`; create
  `events`, `file_artifacts`; backfill `kind='build'` for existing rows.

## R15. Provenance Bundle — v1 (build) and v2 (capture)

```
outputs/bundle/
├── index.html      # self-contained: embeds ALL data via <script id="cairn-data">
├── assets/         # app.css, app.js — NO framework, NO build step
└── (optional) data/  # --split only; default is fully inlined
```

**v1 build bundle** (`cairn_bundle_version: 1`, `kind: build`): step DAG, node lineage, prompts,
models, params — as implemented in Phase 2. Opens via `file://` with no network (ADR 0009).

**v2 capture bundle** (`cairn_bundle_version: 2`, `kind: capture`):

**v2 capture bundle** (`cairn_bundle_version: 2`):

```json
{
  "cairn_bundle_version": 2,
  "kind": "capture",
  "session": { "id", "source", "cwd", "git", "started_at", "model", "usage" },
  "events": [ ... ],
  "files": [
    { "path_rel", "before_hash", "after_hash", "event_seqs": [12, 15, 28] }
  ],
  "graph": {
    "nodes": [{ "id", "type", "label", "seq" }],
    "edges": [{ "from", "to", "kind": "causal"|"data"|"temporal" }]
  },
  "blobs": { "<hash>": "<inline or truncated>" }
}
```

Embedded in `index.html` via `embedding.py` escaper (ADR 0010). Three views: **Files** (default),
**Graph**, **Timeline**. v1 build bundle unchanged for `kind=build`.

## R16. Security & trust model

- **Secrets:** env/`.env`/keychain only; never logged; never in cache keys (only env-var
  *names* in config); `validate` checks presence without echoing values.
- **Untrusted inputs & prompt injection:** source files and tool results are **untrusted
  content**; Cairn never executes instructions found inside them. The risk surface is
  *effectful tools + untrusted corpus*: `validate`/`plan` warn when an effectful agent step
  reads untrusted sources, and recommend pure tools and/or human review. Pinned, reviewable
  trajectories make injection auditable after the fact.
- **MCP:** stdio creds via env; HTTP via OAuth 2.1/PKCE; tool annotations untrusted; no token
  passthrough; `sampling` disabled by default.
- **A2A:** HTTPS + TLS 1.3, verify certificate, identity at the transport layer.
- **CLI agents:** run in a temp working copy; documented as capable of arbitrary side effects;
  `effectful` by default.
- **Network egress** is limited to configured providers, declared MCP HTTP servers, and
  declared A2A endpoints. **No telemetry without explicit opt-in** (off by default).

- **Hook handlers** run as the user; install only via `cairn watch`.
- **Capture bundles** scrub API keys and bearer tokens.
- **Bash tools:** redact env assignments matching `*[Kk][Ee][Yy]*=*`.

## R17. Invariants & edge-case checklist

**Pipeline invariants** (must all hold; each gets a test):

1. Building twice with no changes spends **zero** tokens and zero tool calls.
2. Editing one of N map inputs invalidates **exactly one** child output.
3. A regenerated output that is byte-identical **halts** the downstream cascade.
4. An unchanged dynamic manifest serves **all** children from cache.
5. An **effectful** agent node is **never** silently served from cache.
6. An agent that breaches its budget stops, is marked `budget_exhausted`, and yields partial
   output — never an infinite loop.
7. A failed node writes **no** partial output; re-running resumes via cache hits.
8. Empty corpus / map over zero items → a valid no-op build (no error, zero nodes).
9. A `ref()` to a not-yet-built step is resolved by build order; a cyclic `ref()` is a
   **validate-time** error with the cycle path named.
10. A prompt/policy that renders to empty is a validate-time warning (or error under
    `--strict`).
11. Manifest with duplicate `id`s → hard error.
12. Output-path collisions within a map (two items → same path) → validate-time error.
13. Non-UTF-8 source files are hashed as raw bytes and surfaced to prompts as binary refs (not
    decoded blindly).
14. Very large outputs (> a configurable cap) are stored in CAS but truncated in the inline
    bundle with a "download full" affordance.
15. Concurrent `cairn build` invocations are serialized by the build lock; CAS writes remain
    safe regardless.
16. CAS corruption detected on `--verify` read is treated as a miss + warning, never a silent
    wrong answer.
17. Tokenizer/price gaps degrade gracefully to estimates marked "unpriced", never a hard fail.

**Capture invariants** (each gets a test):

18. Ingest same `external_id` twice → one `runs` row.
19. `cairn hook` always exits 0.
20. Ingest never writes to `action_cache`.
21. `render` deterministic for fixed session + CAS blobs.
22. File paths in bundle are repo-relative, never absolute (except display links).

## R18. Provider & Agent Connection Layer (ergonomics)

> Distilled from the retired **Lattice** project. Lattice was an LLM *transport/proxy* with a
> semantic cache and agent-config patching — **none of which Cairn adopts** (see ADR 0001/0002/
> 0003 and §19). What Cairn *does* take are four self-contained, zero-infra ergonomics patterns
> that make connecting to providers and CLI agents painless. **Hard boundary:** nothing in R18
> may influence action keys, stored outputs, or ledger records (ADR 0002); R18 is about
> *connection convenience and preflight*, not *correctness of the build graph*.

### R18.1 Provider capability registry (`providers/capabilities.py`)

A static, data-driven table mapping `provider → ProviderCapability`, where each entry records:
`default_base_url`, `supported_models` (tuple), `max_context_tokens`, `max_output_tokens`,
feature flags (chat/streaming/tool-calls/multimodal/reasoning/structured-output), `cache_mode`
(none/auto-prefix/explicit-breakpoint/explicit-context — **advisory, transport-only**), and
`RateLimitSemantics` (the provider-specific header names for `retry-after`, request/token
limit/remaining/reset, and whether cache hits count against token limits).

Cairn uses it to: (a) resolve the correct base URL per provider with **zero user config** for
common providers; (b) warn in `validate`/`doctor` when a model is unrecognized or a prompt may
exceed `max_context_tokens`; (c) let the executor read **rate-limit headers by their
provider-specific names** to pace requests (R5 "pre-throttle"); (d) optionally drive
**provider-side prompt caching** as a transport optimization (e.g. Anthropic `cache_control`
breakpoints, OpenAI auto-prefix) **without ever touching the action key** (ADR 0002/0003 §7).

Built-in entries (v1, extensible): `openai`, `anthropic`, `ollama`, `ollama-cloud`, `azure`,
`bedrock`, `gemini`, `vertex`, `groq`, `together`, `deepseek`, `perplexity`, `mistral`,
`fireworks`, `openrouter`, `cohere`, `ai21`. The registry is a pure, frozen dataclass table with
a `register()` hook for user/plugin additions; it is fully unit-testable and contains no I/O.

### R18.2 Credential resolver (`providers/credentials.py`)

Resolves per-provider `api_key` / `base_url` / provider extras with precedence
(highest first): (1) runtime override → (2) user config file
`~/.config/cairn/config.toml` `[providers.<name>]` → (3) **standard industry env-var names**
(the default map: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `OLLAMA_CLOUD_API_KEY`, `GROQ_API_KEY`,
…; base-URL overrides `*_BASE_URL`) → (4) capability-registry default base URL. This is the key
UX win over the bare R3 rule: **the common case is zero-config** — a user who has
`OPENAI_API_KEY` set just works, with no `api_key_env` declaration in `cairn.toml`.

R3 still governs: secrets come **only** from env/config (never committed), are never logged, and
**never enter action keys** — the resolver returns *values* at call time, and the key contains
nothing derived from them. `cairn.toml` may still name a non-standard env var explicitly when a
provider isn't in the default map. `validate`/`doctor` confirm presence without printing values.

### R18.3 Per-provider retry policy tables (`providers/adapters/retry_policies.py`)

The R5 retry classification is realized as **data, not inline conditionals**: a `RetryPolicy` is
an ordered tuple of `RetryRule(matches, max_attempts, backoff, respect_header)`. Backoff
strategies: `from_header("retry-after", fallback=…)`, `exponential(base, cap)`, and
`decorrelated_jitter(base, cap)` (full jitter — mandatory for 529 to avoid synchronized retry
waves, per R5). Built-in policies for `openai` (429 + retry-after, 502/503/504 exponential,
transient-network jitter) and `anthropic` (adds **529 overloaded** exponential), with a sane
default policy for everything else. `retry_policy_for(provider)` selects via the capability
registry. New providers get a policy without touching the executor.

### R18.4 `cairn doctor` + CLI-agent profile registry (`agents/profiles.py`) — Phase 4

**`cairn doctor`** is a no-token preflight (Principle #8, fail-loud): for the current project it
checks resolved provider credentials are present, base URLs/models are recognized (R18.1),
declared MCP servers initialize (R8), and declared CLI-agent binaries are on `PATH`. It prints an
actionable report and exits non-zero if anything required is missing — *before* a build can spend.

**Agent profile registry:** a named table of known CLI agents so a user writes
`backend = "claude-code"` (or `codex`, `cursor`, `opencode`, `copilot`, `generic`) instead of a
raw command template. Each profile knows only how to **detect** the binary (for `doctor`) and how
to **invoke** it for one node — pass the goal, run in the materialized working copy (R10), capture
changed files + transcript. `backend = "cli:<raw-command>"` remains the escape hatch for unknown
agents.

> **Critical boundary (reaffirms ADR 0001):** Cairn's agent profiles are **invocation-only** —
> Cairn subprocesses an agent for the duration of one node and captures its output. Cairn does
> **NOT** mutate the agent's own config, install a proxy, or "route" the agent (Lattice's
> `init`/`lace`/config-patch mechanism is explicitly **not** adopted). No durable changes are
> made to anything the user owns.

### R18.5 What is explicitly NOT taken from Lattice

The proxy/gateway server; durable agent-config patching, `lace`, mutation stores, tunnels;
semantic/approximate response caching (ADR 0002); the multi-transform compression pipeline; the
attribution/influence scorer; any Redis/shared backend. Cairn stays local-first, zero-infra, and
content-addressed. The capability registry's cache semantics are advisory transport hints only
and must never reach the action cache.


**Capture vs Pipeline:** R18 profiles (`claude-code`, `codex`, `cursor`) are for Pipeline CLI-agent **invocation** (Phase 8). **Capture** uses R19 parsers — Cairn does not subprocess agents during ingest.

## R19. Capture & Ingest — full specification

### R19.1 Module layout

```
cairn/ingest/
├── __init__.py
├── writer.py           # sole SQLite mutator for capture
├── normalizer.py       # source-specific events → R7 Event
├── usage.py            # extract ObservedUsage from raw lines
├── hook_cmd.py         # `cairn hook` stdin/stdout
├── watch.py            # install/uninstall/status
├── project_paths.py    # slug resolution, glob discovery
└── parsers/
    ├── claude_code.py
    ├── codex.py
    └── cursor.py
```

### R19.2 Project path slug algorithm

```python
def claude_project_slug(repo_root: Path) -> str:
    return repo_root.resolve().as_posix().replace("/", "-")
    # /Users/harshdaga/cairn → -Users-harshdaga-cairn

def cursor_workspace_slug(repo_root: Path) -> list[str]:
    p = repo_root.resolve().as_posix().strip("/")
    candidates = [
        p.replace("/", "-"),                          # Users-harshdaga-cairn
        "-" + p.replace("/", "-"),                    # -Users-harshdaga-cairn
    ]
    return candidates

def codex_sessions_glob() -> Path:
    return Path.home() / ".codex" / "sessions"
```

`cairn ingest` accepts `--claude-project-dir`, `--cursor-workspace`, `--codex-cwd-filter` overrides.

### R19.3 Claude Code parser

**Input:** path to `*.jsonl`.

**Algorithm:**

```
state = new ParserState()
for line in file:
    obj = json.loads(line)
    match obj.get("type"):
        case "user":
            if tool_result blocks in content → emit tool_result events
            else → emit user_prompt
        case "assistant":
            emit assistant_message from message
            for block in content if tool_use → emit tool_call
        case "system":
            if subtype api_error → emit error
        case "file-history-snapshot":
            emit file_snapshot hint from snapshot.trackedFileBackups
        case _:
            skip
    link parentUuid chain in state
return state.events
```

**Tool arg paths:** `Edit`/`Write`/`MultiEdit` → `tool_input.file_path` or `tool_input.path`.

### R19.4 Claude Code hook wiring

Install merges into existing `hooks` key (backup to `.cairn/watch/claude-settings.bak`).

`cairn hook --event PreToolUse`:

```
stdin  → Claude hook JSON (tool_name, tool_input, session_id, cwd, ...)
action → if Edit|Write|MultiEdit: read file at path → CAS before_hash
       → append_event(tool_call, seq)
stdout → empty
exit   → 0 always
```

### R19.5 Codex parser

**Input:** `rollout-*.jsonl`.

**Algorithm:**

```
on session_meta → begin_session(payload.id, payload.cwd, ...)
on turn_context → set model, turn_id
on event_msg task_started → turn boundary
on event_msg user_message → user_prompt
on response_item message role=assistant → assistant_message
on response_item function_call → tool_call(name, args)
on response_item function_call_output → tool_result
on event_msg task_complete → accumulate usage
```

**apply_patch parsing:** extract paths from patch hunks; `before_hash` from disk at parse time
if file exists (batch) or from hook snapshot (live).

### R19.6 Codex hook wiring

Same events as R19.4 mapping to Codex hook names. `tool_name` may be `apply_patch` — treat as
`edit`. Install uses TOML `[[hooks.…]]` tables per R19.6 in §12.4.

**Trust:** document that user must run `/hooks` → trust Cairn hooks once, or use
`--dangerously-bypass-hook-trust` for automation.

### R19.7 Cursor parser

**Input:** `agent-transcripts/<uuid>/<uuid>.jsonl`.

**Algorithm:**

```
for line in file:
    obj = json.loads(line)
    role = obj.get("role")
    content = obj.get("message", {}).get("content", [])
    if role == "user":
        emit user_prompt from text blocks
    if role == "assistant":
        emit assistant_message from text blocks
        for tool_use blocks → emit tool_call
```

**Subagents:** if `subagents/<id>.jsonl` exists, ingest as child session with
`parent_session_id` and `sub_agent` link.

**agent-tools/ enrichment (Phase 6):** if `agent-tools/<id>.txt` exists, map to `tool_result`
inline by matching tool call order.

### R19.8 `cairn hook` command contract

```
cairn hook --event <HookEventName> --source <claude-code|codex>
```

- Reads JSON from stdin (full hook payload).
- Resolves project root: `cwd` from payload → `git rev-parse --show-toplevel` (fallback: cwd).
- Opens `.cairn/ledger.db` in project; calls `writer.py`.
- **Never** prints secrets to stdout.
- **Always** exit 0.

### R19.9 `cairn watch install` contract

1. Detect sources: `--source` or all.
2. For Claude: patch `.claude/settings.local.json` hooks (§12.3).
3. For Codex: patch `~/.codex/config.toml` or project `.codex/config.toml` (§12.4).
4. Write `.cairn/watch/install.json` with installed commands + backup paths.
5. `uninstall` restores backups.

### R19.10 Session graph linker (`graph/session_graph.py`)

```
Input: events[] ordered by seq
Output: { nodes, edges }

nodes = one per event (or collapsed "turn" nodes for UI)
edges:
  temporal: seq i → seq i+1
  causal: tool_call.tool_use_id → tool_result.tool_use_id
  data: file_snapshot(read) at seq a → tool_call(write) at seq b if same path_rel
        and no intervening write
  delegation: sub_agent → child session root event
```

Collapse policy for bundle UI: consecutive assistant_message + tool_calls within same turn
→ single "Turn N" super-node (optional, renderer config).

---

*End of charter v2.0. Build exactly what's written here. When tempted to add undeclared scope,
check §4, §12.7, and §19 first.*
