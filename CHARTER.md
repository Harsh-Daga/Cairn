# Cairn — Project Charter & Technical Design

> **The definitive open-source inference workspace for AI agents and direct LLM/provider workflows.**
>
> Cairn unifies project context, workflows, agent capture, provider execution, artifacts, and
> explainable reports — connected through lineage. Local-first by default. Git-native. One binary.

**Status:** v3.0 — inference workspace charter (Phases 0–1 complete; implementation in progress)  
**License:** Apache-2.0  
**Audience:** contributors, integrators, and users building on Cairn without reading source first.

---

## 0. How to read this document

| Section | Contents |
|---------|----------|
| §1–§3 | Problem, core idea, positioning |
| §4 | Design principles |
| §5–§6 | Domain model and on-disk layout |
| §7 | Worked examples |
| §8–§14 | System architecture (one section per major system) |
| §15 | Unified observability model |
| §16 | CLI, API, SDK surfaces |
| §17–§18 | Testing and security |
| §19 | 22-phase build plan with exit criteria |
| §20 | Success metrics and non-goals |
| Part II (R1–R19) | Normative implementation spec (formats, algorithms, parsers) |

**Three execution surfaces, one observability model:**

| Surface | Entry | Primary artifact |
|---------|-------|------------------|
| **Capture** | `cairn ingest` / `cairn watch` | Session provenance bundle |
| **Pipeline** | `cairn build` | Build outputs + lineage bundle |
| **Workspace** | `cairn live serve` / HTTP API | Live + historical inference UI |

Agent sessions and provider runs produce **identical report shapes**. Users do not need to know
which runtime executed the work.

---

## 1. The Problem

Developers use Claude Code, Codex, Cursor, OpenHands, and direct API calls interchangeably.
Work spans markdown specs, source code, documents, and generated artifacts — but provenance is
fragmented across JSONL logs, chat exports, git diffs, and SaaS dashboards.

**Pain:**

1. No unified audit trail across agents and providers
2. No shareable explanation of *what happened* without pasting raw prompts
3. No causal graph linking context → tools → artifacts → outputs
4. No local, offline, reproducible inference workspace
5. Repeatable workflows require re-prompting instead of versioned definitions

**Cairn solves this** as a local-first inference workspace: record, execute, explain, and share —
with optional collaboration and VCS integration.

---

## 2. The Core Idea

Every inference execution is a **directed acyclic graph**:

```
Context → Prompt/Workflow → Execution (agent or provider) → Tool calls → Artifacts → Report
```

Cairn **infers or declares** this graph, stores it in an append-only ledger + content-addressable
store, and renders **explainable reports** (summary, narrative, tool usage, artifact inventory,
execution/artifact/dependency DAGs, reproducibility metadata).

**Product equation:** GitHub (context + VCS) + Notion (docs + knowledge) + Build System
(cached pipelines) + Agent Observability + Inference Workspace — unified through lineage.

---

## 3. Prior Art & Positioning

| Category | Examples | Cairn difference |
|----------|----------|------------------|
| Agent inspectors | claude-devtools, Chronicle | Cross-agent, offline bundles, file-centric DAG |
| Cloud observability | Langfuse, Braintrust | Local-first, no account required |
| Build systems | dbt, Make | LLM-native DAG with content-addressed cache |
| Agent runtimes | LangGraph, CrewAI | Cairn records and builds; does not replace runtimes |

**Cairn builds:** cross-agent ingest, unified trajectory model, provenance bundles, workflow
engine, provider framework, execution graphs, artifact registry, reporting, optional collaboration.

**Cairn reuses:** git, agent transcript formats, hooks APIs, Jinja2, HTTP provider APIs.

---

## 4. Design Principles

1. **Local-first, zero-infra default** — no server required for capture, build, or offline reports
2. **Capture fails open; build fails loud** — hooks never block agents; validate/doctor block spend
3. **Provenance is the product** — traceability over slick output
4. **Unified observability** — agent and provider runs share ledger, CAS, trajectory, renderer
5. **DAG is inferred or declared** — never hand-maintained in capture; `ref()`/`source()` in pipeline
6. **No lock-in** — delete Cairn; keep repo, logs, git history
7. **Boring technology** — Python, SQLite, SHA-256, vanilla JS, subprocess hooks
8. **Zero-config capture** — `cairn ingest` works without `cairn.toml`
9. **Explainability over raw prompts** — turn cards, graphs, narratives as default
10. **Extensible agent/provider registry** — new parsers and adapters without core changes

---

## 5. Domain Model

### 5.1 Core entities

| Entity | Definition |
|--------|------------|
| **Project** | Directory scoped to Cairn; git root; holds context, workflows, `.cairn/` store |
| **Context asset** | Any managed input: markdown, source, document, context file, knowledge asset |
| **Workflow** | Versioned definition: steps, prompts, context selectors, execution template |
| **Session** | One continuous agent conversation or provider run |
| **Event** | Normalized ledger row: prompt, message, tool_call, tool_result, file_snapshot, etc. |
| **Trajectory** | Ordered events for one session or workflow node |
| **Artifact** | First-class output: report, summary, generated file, code, asset (CAS-backed) |
| **Run** | One build, capture ingest, or provider workflow execution (`runs.kind`) |
| **Report** | Rendered explainability bundle: summary + narrative + graphs + reproducibility |
| **Snapshot** | Point-in-time project/session state for diff and versioning |
| **Lineage edge** | Relationship: derived_from, read, wrote, invoked, depends_on |

### 5.2 Graph types

| Graph | Scope | Edges |
|-------|-------|-------|
| **Execution graph** | Single session/run | temporal, causal, delegation |
| **Artifact graph** | Artifacts across runs | produced_by, derived_from |
| **Dependency graph** | Pipeline workflows | ref(), source(), map/reduce |
| **Lineage graph** | Project-wide | unified view for reports |

### 5.3 Agent sources (registry)

| Source ID | Batch ingest | Live hooks | Status |
|-----------|-------------|------------|--------|
| `claude-code` | Yes | Yes | Implemented |
| `codex` | Yes | Yes | Implemented |
| `cursor` | Yes | Tail watcher | Implemented |
| `hermes` | Yes | Tail watcher | Implemented |
| `aider` | Planned | Planned | Phase 8 |
| `openhands` | Planned | Planned | Phase 8 |
| `goose` | Planned | Planned | Phase 8 |

### 5.4 Provider registry

| Provider | Adapter | Status |
|----------|---------|--------|
| `openai` | HTTP OpenAI | Implemented |
| `anthropic` | HTTP Anthropic | Implemented |
| `ollama` / `ollama-cloud` | HTTP Ollama | Implemented |
| `groq` | HTTP Groq | Implemented |
| `gemini` | HTTP Google AI | Phase 9 |
| `openrouter` | HTTP OpenRouter | Phase 9 |
| `openai-compatible` | Generic HTTP | Implemented (fallback) |

---

## 6. On-Disk Layout

```
my-project/
├── cairn.toml              # optional: project config, workflows, providers, agents
├── context/                # or inputs/: managed context assets
│   ├── docs/
│   ├── src/
│   └── knowledge/
├── prompts/                # project prompts (links to registry)
├── workflows/              # versioned workflow definitions (Phase 7)
├── outputs/                # generated artifacts
│   └── bundle/             # rendered reports
└── .cairn/                 # GENERATED — gitignored
    ├── ledger.db           # runs, events, artifacts, workflows, sessions
    ├── cache/cas/<aa>/<hash>
    ├── sessions/<id>.json
    ├── runs/<id>.json
    ├── snapshots/<id>/     # Phase 15
    ├── prompts/registry/   # Phase 6
    └── watch/              # hook state, ingest cursors
```

**Coexistence:** Capture sessions, provider runs, and pipeline builds share one `ledger.db`,
distinguished by `runs.kind`: `capture` | `build` | `provider`.

**Invariant (ADR 0008):** ingest events never write action-cache entries.

---

## 7. Worked Examples

### 7.1 Agent capture (zero config)

```bash
cd my-repo
cairn ingest                    # import latest agent sessions
cairn sessions                  # list with tokens, files, branch
cairn render --session <id>     # offline HTML report
```

### 7.2 Direct provider workflow

```bash
cairn init my-project && cd my-project
# edit cairn.toml workflow + prompts
cairn validate && cairn doctor
cairn build --yes               # provider execution
cairn render --run <id>         # same report shape as capture
```

### 7.3 Live workspace

```bash
cairn watch install --source all
cairn live serve                # SSE updates at localhost:8787
# work in any agent; report updates in browser
```

### 7.4 Share and reproduce

```bash
cairn render --zip -o report.zip
cairn snapshot create           # Phase 15
cairn workflow run summarize@v2 --context docs/brief.md
```

---

## 8. Project Context System (Phase 5)

### Architecture

`cairn/context/` indexes all project assets by path, MIME, git state, and content hash.
Integrates with `loader/sources.py` and `ingest/project_paths.py`.

### Interfaces

```python
class ContextRegistry:
    def scan(project: Project) -> list[ContextAsset]: ...
    def resolve(selector: str) -> ContextAsset: ...
    def exclude(patterns: list[str]) -> None: ...
```

### Flows

1. `cairn init` scaffolds `context/` and `cairn.toml` exclusions
2. `cairn context scan` refreshes index in ledger
3. Workflows select context via glob, path, or tag selectors
4. Capture links file artifacts to context assets by repo-relative path

### Storage

- `context_assets` table: path, hash, mime, git_blob, tags, updated_at
- Large blobs in CAS; metadata in SQLite

### APIs

- CLI: `cairn context list|scan|show`
- SDK: `cairn.context.scan(project_root)`

### Integration

- Git: optional `git_commit` pinning per session/run
- Workflows: context selectors in workflow YAML
- Reports: Files tab maps to context assets

### Lifecycle

Create on scan → update on hash change → soft-delete on removal → GC when unreferenced

---

## 9. Prompt Registry (Phase 6)

### Architecture

`cairn/prompts/` manages reusable prompts with versioning, front matter (model/params), and
project/library scope.

### Interfaces

```python
class PromptRegistry:
    def register(prompt: PromptDef) -> PromptRef: ...
    def get(name: str, version: str | None) -> PromptDef: ...
    def list(library: str | None) -> list[PromptRef]: ...
```

### Storage

- `.cairn/prompts/registry/<name>/<version>.json` + CAS body
- `prompt_refs` table for workflow linkage

### Flows

1. Author prompt in `prompts/` or `cairn prompt add`
2. Version bump creates immutable version
3. Workflow references `prompt://summarize@v2`
4. Build/render resolves and pins version in run record

### APIs

- CLI: `cairn prompt list|show|add|diff`
- SDK: `cairn.prompts.get(name, version)`

### Lifecycle

Immutable versions; deprecation flag; no deletion of referenced versions

---

## 10. Workflow Engine (Phase 7)

### Architecture

`cairn/workflow/` executes versioned workflow definitions: chat steps, map/reduce, agent nodes
(Phase 8), dynamic manifests.

Extends `executor/runner.py`, `graph/builder.py`, `plan/planner.py`.

### Interfaces

```python
class WorkflowEngine:
    def validate(workflow: WorkflowDef) -> ValidationResult: ...
    def plan(workflow: WorkflowDef, context: ContextSelection) -> ExecutionPlan: ...
    async def execute(plan: ExecutionPlan, provider: Provider) -> RunRecord: ...
```

### Storage

- `workflows/<name>/<version>.yaml` in project
- `workflow_runs` links run → workflow version + context digest

### Flows

```
Prompt → Context Selection → Workflow → Model Execution → Artifacts → Report → Graph
```

### APIs

- CLI: `cairn workflow list|validate|run|history`
- Reuses `cairn build` for pipeline-compatible workflows

### Lifecycle

Draft → validated → executed → archived; graduation from capture patterns (Phase 8)

---

## 11. Agent Integration Framework (Phase 8)

### Architecture

`cairn/agents/` provides parser plugin interface, normalizer, hook installer, live tail,
session reconstruction, and replay.

### Interfaces

```python
class AgentParser(Protocol):
    source_id: str
    def parse_events(raw: Iterator[dict]) -> Iterator[NormalizedEvent]: ...
    def external_id(raw: dict) -> str: ...
```

### Flows

| Mode | Flow |
|------|------|
| Live attachment | hooks/tail → `hook_cmd` → ledger (in_progress) |
| Historical import | JSONL → parser → normalizer → writer |
| Reconstruction | events → trajectory CAS → session_graph |
| Replay | read-only re-render from ledger |

### Storage

Reuses ingest tables: `events`, `tool_calls`, `file_artifacts`, `trajectories`

### APIs

- CLI: `cairn ingest`, `cairn watch`, `cairn hook`, `cairn sessions replay`
- SDK: `cairn.agents.ingest(source, path)`

### Integration design

- Claude Code: hooks in `.claude/settings.local.json` (R19)
- Codex: hooks + rollout JSONL (R19)
- Cursor/Hermes: tail watchers on transcript paths (R19)
- Aider/OpenHands/Goose: new parsers per Phase 8

### Lifecycle

Session: `in_progress` → `completed` | `error`; cursor-based incremental ingest

---

## 12. Provider Framework (Phase 9)

### Architecture

`cairn/providers/` implements `Provider` protocol, registry, credentials, HTTP adapters,
recorded replay for CI.

### Interfaces

```python
class Provider(Protocol):
    async def complete(request: CompletionRequest) -> CompletionResponse: ...
```

### Flows

Direct provider workflow mirrors agent capture output:

1. Select context + workflow
2. Execute via provider adapter
3. Write run record with tokens, latency, model
4. Store outputs as artifacts
5. Render unified report

### Storage

- Completions stored in CAS; usage in `nodes` table
- Recorded fixtures in `cairn/data/fixtures/`

### APIs

- CLI: `cairn build`, `cairn doctor`, `--provider-mode recorded|live`
- SDK: `cairn.providers.get(name)`

### Lifecycle

Credential check → retry policy → completion → ledger write → artifact registration

---

## 13. Execution Graph Engine (Phase 10)

### Architecture

`cairn/graph/session_graph.py` extended for execution, artifact, and dependency DAGs.
`cairn/render/graph_layout.py` renders SVG with pan/zoom.

### Interfaces

```python
def build_execution_graph(events: list[Event]) -> Graph: ...
def build_artifact_graph(artifacts: list[Artifact]) -> Graph: ...
def build_dependency_graph(workflow: WorkflowDef) -> Graph: ...
```

### Storage

Graphs computed at render time from ledger; optional cached JSON in CAS for large sessions

### Reports

Three graph visualizations per execution (§15); hash deep links `#event/N`, `#artifact/<hash>`

---

## 14. Artifact System (Phase 11)

### Architecture

`cairn/model/artifact.py` + `cache/store.py` unified registry for all generated outputs.

### Interfaces

```python
class ArtifactRegistry:
    def register(artifact: Artifact) -> str: ...  # returns hash
    def get(hash: str) -> Artifact: ...
    def lineage(hash: str) -> LineageGraph: ...
```

### Storage

- `artifacts` table: hash, kind, path, mime, run_id, session_id, metadata
- Blob in CAS

### Lifecycle

Register on write → link to run/session → include in report inventory → GC per retention policy

---

## 15. Unified Observability Model

Every execution record contains:

**Inputs:** files, prompts, context digests  
**Execution:** provider/agent, model, tool calls, latency, token usage, reasoning metadata  
**Outputs:** artifacts, generated files, reports  
**Relationships:** lineage, dependency, execution edges  

**Report sections (mandatory):**

1. Summary — what was accomplished
2. Execution narrative — what happened (turn cards, not raw JSON)
3. Tool usage — tools called with outcomes
4. Artifact inventory — generated outputs with hashes
5. Graph visualizations — execution, artifact, dependency DAGs
6. Reproducibility metadata — workflow version, context digest, model, params, git commit

**Bundle versions:**

| Version | Mode | Status |
|---------|------|--------|
| v1 | Pipeline build | Implemented |
| v3 | Capture session | Implemented |
| v3-live | Live session | Phase 13 |

---

## 16. Reporting & Visualization (Phases 12–13)

### Architecture

`cairn/render/` produces self-contained HTML (`file://` safe), optional zip, secret scrubbing.

### Live workspace (Phase 13)

`cairn/live/` — HTTP server, SSE event stream, browser auto-refresh via `capture.js`.

```
cairn live serve --port 8787
GET /session/<id>        → HTML shell
GET /session/<id>/events → SSE stream
```

### Shareability

| Mode | Mechanism |
|------|-----------|
| Public report | Export zip; no secrets (scrub.py) |
| Private report | Local only; optional encryption Phase 19 |
| Snapshot | Phase 15 point-in-time export |
| Reproducibility | Run record + workflow version + context digest |

---

## 17. Collaboration & Versioning (Phases 14–15)

### Collaboration (Phase 14)

Optional sync layer — **not required for local-first default**.

- `cairn/collab/` — file-based sync protocol (Syncthing-compatible layout) or HTTP relay
- Shared project state via exported ledger snapshots
- Session awareness via `sessions` table + sync cursor
- No accounts in v1; team share via git + bundle exports

### Snapshots & VCS (Phase 15)

- `cairn snapshot create|list|diff|restore`
- Pin `git_commit` on runs; optional `cairn diff --session A B`
- Version history via append-only ledger + snapshot CAS roots

---

## 18. CLI, API, SDK (Phases 16–18)

### CLI (Phase 16)

Unified command groups:

```
cairn init | validate | doctor | status
cairn context * | prompt * | workflow *
cairn ingest | watch | hook | sessions
cairn build | plan | runs
cairn render | graph | live *
cairn snapshot *
```

### HTTP API (Phase 17)

```
GET  /v1/projects/{id}/sessions
GET  /v1/sessions/{id}
GET  /v1/sessions/{id}/events     (SSE)
POST /v1/workflows/{id}/run
GET  /v1/runs/{id}/report
```

Local bind `127.0.0.1` by default; auth hooks in Phase 19.

### Python SDK (Phase 18)

```python
import cairn
project = cairn.Project.open(".")
run = cairn.workflow.run("summarize", context="docs/")
report = cairn.render.html(run)
```

Public API exported from `cairn/__init__.py`; stable SemVer from 1.0.

---

## 19. Security & Performance (Phases 19–20)

### Security (Phase 19)

- Secret scrubbing in bundles (`render/scrub.py`) — implemented
- Credential env-var only (R3) — implemented
- Optional report encryption, ACLs for shared relay
- Hook subprocess sandboxing guidelines

### Performance (Phase 20)

- CAS read cache, graph layout memoization
- Incremental ingest cursors
- Parallel build concurrency (implemented)
- Large session streaming render

---

## 20. 22-Phase Build Plan

| Phase | Name | Exit criteria |
|-------|------|---------------|
| **0** | Vision Validation | `docs/phase-0-vision-validation.md`; requirements mapped |
| **1** | Architecture Audit | `docs/architecture-audit.md`; every file classified |
| **2** | Charter Rewrite | This document v3.0; no placeholders |
| **3** | Domain Model | `model/workflow.py`, `model/artifact.py`, `model/session.py`; tests |
| **4** | Storage Layer | Ledger schema v4; migration; tests |
| **5** | Project Context System | `cairn/context/`; CLI; tests |
| **6** | Prompt Registry | `cairn/prompts/`; versioning; tests |
| **7** | Workflow Engine | `cairn/workflow/`; `cairn workflow run`; tests |
| **8** | Agent Integration Framework | Aider/OpenHands/Goose parsers; replay; tests |
| **9** | Provider Framework | Gemini, OpenRouter adapters; tests |
| **10** | Execution Graph Engine | Artifact + dependency DAGs; tests |
| **11** | Artifact System | Registry; lineage; tests |
| **12** | Reporting Engine | Unified report schema agent+provider; tests |
| **13** | Visualization Layer | `cairn live serve`; SSE; tests |
| **14** | Collaboration Layer | Sync protocol; session export; tests |
| **15** | Snapshot & Versioning | `cairn snapshot`; session diff; tests |
| **16** | CLI | All command groups; e2e CLI tests |
| **17** | API | HTTP server; OpenAPI spec; tests |
| **18** | SDK | Stable public API; docs |
| **19** | Security | Audit; encryption option; docs |
| **20** | Performance | Benchmarks; profiling; targets met |
| **21** | Documentation | README, guides, API docs match implementation |
| **22** | Production Validation | E2E user journey; delete `spike/`; release 1.0 |

**After every phase:** build → test → lint → update docs → commit.

---

## 21. Success Metrics

1. User runs `cairn ingest` → `cairn render` → understands session without reading raw JSON
2. User runs `cairn build` → identical report shape to capture
3. All 121+ tests pass; mypy strict clean; ruff clean
4. Offline `file://` bundle works without network
5. New agent parser addable without core changes
6. Charter and implementation match (no drift)

---

## 22. Non-Goals

- Replacing agent runtimes (Claude Code, Cursor, etc.)
- Cloud-hosted observability SaaS as default
- Real-time collaborative editing (Google Docs model)
- Model training or fine-tuning
- IDE plugin (CLI + HTML report is the product)

---

*Part II (R1–R19) — Detailed Engineering Reference follows.*

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
  source: "claude-code" | "codex" | "cursor" | "hermes" | "builtin" | "a2a" | ...,
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

### R19.11 Hermes parser

**Input:** `~/.hermes/sessions/session_*.json`.

**Algorithm:**

```
data = json.load(file)
external_id = data["session_id"]
for message in data["messages"]:
    if role == "user" and not compaction handoff:
        emit user_prompt from content
    if role == "assistant":
        emit assistant_message from content (+ optional reasoning)
        for tool_calls → emit tool_call (normalize names per §12.5.1)
    if role == "tool":
        emit tool_result linked by tool_call_id
```

**Project filter:** include file only if `hermes_session_matches_project(path, repo_root)`.

**Idempotency:** skip when `(source=hermes, external_id=session_id)` exists in ledger.

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
→ single "Turn N" super-node (required in v3; §11.8.3).

### R19.12 Bundle renderer v3 (`render/capture_bundle.py`, `render/assets/`)

**Input:** session row + `events[]` + `file_artifacts[]` + precomputed `graph`.

**Output:** self-contained `index.html` + `assets/` with embedded or sidecar JSON.

**Build steps:**

```
1. Resolve session identity (R19.14) → session header object
2. assign_seq if not already numbered
3. build_turns(events) → turns[] per §11.8.3
4. enrich_files(file_artifacts, events, cas) → diff_preview, snapshot_quality
5. layout_graph(graph, turns) → node x,y positions (layered DAG)
6. scrub_secrets(all inline text fields)
7. emit bundle JSON (cairn_bundle_version: 3)
8. render HTML shell + app.js bootstraps from embedded JSON
```

**`build_turns` algorithm:**

```
turns = []; current = null
for event in events ordered by seq:
    if event.type == user_prompt:
        if current: turns.append(current)
        current = { turn_id: len(turns)+1, user: event, tools: [], assistant: null }
    elif current is null:
        continue  # skip orphan pre-session noise
    elif event.type == assistant_message:
        current.assistant = merge(current.assistant, event)
    elif event.type in (tool_call, tool_result):
        current.tools.append(event)
    elif event.type == session_end:
        break
if current: turns.append(current)
```

**Graph layout:** topological sort by temporal edges; assign layers by seq; file nodes in
side column; store `{id, x, y, layer}` on each node.

**Tests:** golden `tests/fixtures/render/capture_v3_mini.html`; assert no external URLs;
assert session header contains `external_id` + `session_key`; graph has positioned nodes.

### R19.13 Live capture (`ingest/live/`)

**Module layout:**

```
cairn/ingest/live/
  __init__.py
  tail.py          # generic file tail with debounce
  cursor_tail.py   # agent-transcripts/**/*.jsonl
  hermes_tail.py   # session_*.json growing file
  server.py        # localhost HTTP + SSE for cairn live serve
  reconcile.py     # recover partial sessions from disk
```

**Tail watcher contract:**

```
on_file_change(path):
    debounce 500ms
    parsed = parser.parse_incremental(path, last_offset)
    for event in parsed.new_events:
        writer.append_event(run_id, event)  # in_progress session
    update last_offset in .cairn/watch/tail-state.json
```

**SSE event shapes:**

```
event: append
data: {"seq": 42, "type": "tool_call", "name": "edit", …}

event: finish
data: {"status": "completed", "external_id": "…", "event_count": 313}
```

**Idle timeout:** no new events for `capture.live.idle_timeout_s` (default 300) → `finish_session(failed|completed)`.

### R19.14 Session identity resolution

**Ingest:** `UNIQUE(source, external_id)` on `runs` (existing).

**Display priority in bundle header:**

1. `external_id` (primary title)
2. `source` badge
3. `session_key` = `f"{source}:{external_id}"` (subtitle, copyable)
4. `run_id` (footer, for support)

**CLI resolution (`render`, `show`, `graph`, `live serve`):**

```
resolve_session_id(project, arg):
    if arg matches run_id pattern → lookup by run_id
    if arg matches external_id → lookup by (source, external_id) if --source given
                              else lookup unique external_id across sources
                              else error: ambiguous, pass --source
    if arg matches session_key "source:external_id" → split and lookup
```

**`cairn sessions` columns:** `EXTERNAL_ID`, `SOURCE`, `STATUS`, `EVENTS`, `STARTED`, `RUN_ID` (verbose).

**Timestamps:** prefer ISO-8601 from agent metadata; fallback `started_at` from first event seq;
never show raw `line:1` in v3 bundle (map to ingest time or file mtime).

---

*End of charter v2.0. Build exactly what's written here. When tempted to add undeclared scope,
check §4, §12.7, and §19 first.*
