# Cairn — Project Charter & Technical Design

> **A build system for LLM computation over a corpus of files — including agentic and multi-agent workflows.**
> Declare your inputs, prompts, and the pipeline that connects them. Cairn runs the
> pipeline, re-computing only what changed, caches every result by content, and
> compiles a self-contained, reproducible, shareable artifact that records exactly
> how every output — and every agent trajectory — was produced.

> *"dbt for LLM work."* Local-first. Git-native. Zero infrastructure. One binary.

**Status:** Draft v1.2 — implementation-ready charter (adds agentic/multi-agent design; adds
provider & agent connection ergonomics in R18, distilled from the retired Lattice project)
**License (intended):** Apache-2.0
**Audience:** anyone who wants to build the whole thing from this document alone.

---

## 0. How to read this document

This charter is the single source of truth. It is ordered so you can build top to
bottom:

1. **Why** (§1–§3) — the problem, the one core idea, and how we're positioned.
2. **What** (§4–§7) — principles, the domain model, and the exact on-disk format.
3. **How** (§8–§12) — architecture, the cache-key algorithm, the CLI, the flows, and the
   agentic / multi-agent design.
4. **Build it** (§13–§19) — stack, coding rules, testing, the phase plan, risks, and
   how we know it worked.
5. **Appendix** (§20) — a full worked example and the config schema.
6. **Part II — Detailed Engineering Reference** (R1–R18) — the no-ambiguity implementation
   spec: exact formats, algorithms, protocols, and edge cases for every component, plus the
   provider & agent connection layer (R18). Build from Part II; let Part I's principles (§4)
   govern when they conflict.

If a decision isn't written here, the default is: **do the boring, local, file-based,
reversible thing.**

---

## 1. The Problem (and the evidence behind it)

There is a recurring shape of project: *"I have a body of files, I want to run LLM
computation over them in an iterated way, and some of the outputs are deliverables
worth keeping and sharing."* Research synthesis, document generation, codebase
analysis, content pipelines, knowledge-base construction, due diligence — and,
increasingly, **agentic workflows** where one or more autonomous agents plan, call
tools, and produce results over that same corpus.

Today there are exactly two ways to do this, and both are bad:

- **The manual way** — paste into a chat interface N times, or kick off an agent and
  copy its output. Unrepeatable. No record of what produced what. Editing one prompt
  means redoing everything by hand.
- **The code way** — write a script with a hand-rolled cache, or stand up a heavyweight
  orchestrator (LangGraph, Dagster, Prefect, CrewAI). Now you maintain plumbing, and you
  *still* hand-roll the "only re-run what changed" logic, because those frameworks give
  you state snapshots for fault-tolerance, **not** content-keyed memoization that skips
  unchanged steps.

In both cases the output is **ephemeral**: when you hand someone a result, there is no
portable record of which inputs, which prompt, which model — and for agents, which
tools and which trajectory — produced it.

**This pain is real and widely felt.** The market shows a long tail of small,
single-purpose open-source utilities solving fragments of it, plus first-hand
practitioner accounts of the exact pains: lost context across sessions, no audit trail,
"what was the original prompt / what did I decide / why this approach," silent quality
regressions, and — for multi-agent systems specifically — opaque trajectories and
cost/observability failures (a large share of agentic pilots fail on infrastructure and
observability, not on model quality). People keep building crappy partial versions of
this for themselves.

**This pain is *not* well-served as a single, tasteful, general tool.** The components
exist separately; the connective tissue does not. That gap is Cairn.

---

## 2. The Core Idea (one paragraph, memorize it)

A pipeline of LLM computations over files is a **directed acyclic graph (DAG)**: sources
flow into prompts, prompts produce outputs, outputs feed downstream prompts. Build
systems (Make, Bazel, dbt) have solved "recompute only the changed parts of a DAG" for
decades, using **content-addressing**: hash the inputs of each node; if the hash is
unchanged, reuse the cached output. The reason this has never been cleanly applied to
LLM work is that **an LLM call is not hermetic** — the same input can produce different
output. **Cairn's core move is to impose hermeticity by content-addressing the
*realized* output**: the first time a node runs, we record its output keyed by the hash
of `(resolved prompt + model + params + upstream input hashes)`. On every subsequent
build, if that key is unchanged, we reuse the realized output verbatim. You opt into
re-rolling explicitly. This converts "I ran an LLM once" into a **reproducible, cacheable,
auditable, shareable artifact**. The same move extends, unchanged, from a single
completion to **an entire agent trajectory** (§12) — which is the thing no existing tool
packages.

Everything else in Cairn is in service of that idea or reuses something that already
exists.

---

## 3. Prior Art & Positioning (what we reuse vs. what we build)

Honest map of the neighborhood. **We do not rebuild owned territory.**

| Tool / category | What it nails | Why it isn't Cairn |
|---|---|---|
| **dbt** | The *shape*: CLI, `ref()`-driven DAG, materializations, incremental builds, tests, lineage docs, git-native. | SQL-and-warehouse only. We borrow the shape wholesale and retarget it at files + prompts + model/agent calls. |
| **Bazel / Nix** | The *engine*: Merkle-DAG, action cache + content-addressable store, hermetic reuse. | Built for deterministic compilation; no notion of prompts, models, or non-determinism. We borrow the caching model and adapt it to non-hermetic LLM/agent calls. |
| **Dagster / DVC / Prefect** | Content-addressed asset versioning, incremental materialization, dynamic outputs. | Heavyweight (servers, Kubernetes, data-engineering worldview). Not LLM-native. Not zero-infra. Not a single binary. Not aimed at a writer/researcher/analyst. |
| **promptfoo** | Local-first, single version-controlled config, content-cached, only-external-call-is-the-model. | *Evaluation*-focused (test prompts against assertions), not *production* of a corpus of deliverable artifacts over a DAG. Validates our ergonomics; confirms the gap. |
| **LangGraph / CrewAI / AutoGen / ADK** | *Agent runtimes*: execute the agent loop, manage in-flight state, implement supervisor/swarm/handoff topologies. | They *run* agents; they don't make agent runs reproducible, content-addressed, cached, or shareable. Cairn **wraps and composes** them (§12), it does not replace them. |
| **MCP / A2A (Linux Foundation AAIF)** | The interop standards: MCP = agent↔tools; A2A = agent↔agent. | These are *protocols*, not a build tool. Cairn *speaks* them rather than inventing its own (§12.8). |
| **Latitude / Braintrust / PromptLayer** | Prompt versioning, collaboration, eval, deploy-as-endpoint. | SaaS platforms; the unit is a deployed prompt/endpoint, not a reproducible build artifact over your own files. |
| **Elicit** | Reproducible, auditable, *shareable-with-anyone* research process — exactly our provenance artifact. | Locked to the literature-review vertical. We generalize the capability. |
| **llm-context / llmcxt / PromptMage / CONTEXT.md, etc.** | Real signal that the pain exists; people build these by hand. | Fragmentary, single-feature, no DAG, no caching, no provenance, no shareable artifact. |

**What Cairn reuses and never builds:**

- **git** — for versioning, history, snapshots, branching, and human collaboration. The
  whole Cairn project is plain text files; git *is* the collaboration layer in v1.
- **Model provider APIs / SDKs** — for inference. We wrap them behind a thin adapter.
- **Agent runtimes & coding agents** (Claude Code, Codex, LangGraph, CrewAI, external
  A2A agents) — a Cairn node can *invoke* an agent; we never build an agent runtime.
- **MCP** — for giving agent nodes tools; **A2A** — for invoking external agents.
- **Jinja2** — for prompt templating (same proven choice as dbt and promptfoo).
- **Dagster (optional, later)** — as a heavy-duty execution backend for users who
  outgrow the built-in local runner. Default is our own runner.

**What Cairn builds (the glue nobody has unified):**

1. A minimal, readable, git-native **project format** for "a corpus + a prompt library +
   a pipeline + outputs," including agent and dynamic steps.
2. A **content-addressed, LLM-native, zero-infra build engine** that recomputes only
   what changed — and pins non-deterministic completions *and agent trajectories*.
3. A **diff/inspect** experience — "make + git diff for inference."
4. A **self-contained, reproducible, shareable provenance artifact** — including full,
   recursive agent/sub-agent trajectories — as a first-class build output.

---

## 4. Design Principles & Ground Rules

These are non-negotiable. Every design decision is checked against them.

1. **Local-first, zero-infra.** Cairn runs on a laptop with no server, no database, no
   container, no account. The only network calls are to model providers, MCP tools, and
   (optionally) external A2A agents. If a feature requires standing up infrastructure, it
   does not belong in the core.
2. **Everything is plain text in a git repo.** Inputs, prompts, config, and the run
   ledger are human-readable files. No hidden binary state that git can't diff.
3. **Content-addressed and reproducible by default.** Same inputs ⇒ same cached output
   (or trajectory), every time, until the user explicitly asks to re-roll. Determinism is
   the default; non-determinism is opt-in and visible.
4. **Do one thing well; compose, don't absorb.** Cairn is a build tool. It is not an
   editor, a notebook, an eval platform, a vector DB, an agent runtime, or a SaaS. It
   shells out to those; it doesn't reimplement them.
5. **The DAG is inferred, never hand-maintained.** Like dbt's `ref()`, dependencies are
   declared by reference at the point of use. Users never maintain a separate graph file.
6. **No lock-in, fully reversible.** Outputs are normal files. The cache is a normal
   directory. Deleting Cairn leaves you with all your inputs, prompts, and outputs intact.
7. **Boring technology.** Prefer mature, well-understood tools (Jinja2, SQLite, SHA-256,
   git, MCP, A2A). Novelty budget is spent only on the core idea (§2), not infrastructure.
8. **Fail loud, fail cheap.** Validate the whole project before spending a single token.
   Always show what *would* run and the estimated cost before running it. Agent budgets
   and iteration caps are mandatory, not optional.
9. **Taste: a 5-line project should take 5 minutes.** The smallest useful project must be
   tiny. Complexity (including agents) is opt-in and layered, never front-loaded.
10. **Provenance is not a feature, it's the product.** Every output carries its full
    lineage — including, for agents, the complete recursive trajectory. If we ever have to
    choose between a slick output and a traceable one, we choose traceable.
11. **Prefer a step to an agent.** If a unit of work is deterministic, it's a step, not an
    agent. Agents are reserved for genuinely autonomous work, because they cost more and
    are harder to reproduce. Cairn nudges users toward plain steps.

---

## 5. Domain Model (the vocabulary)

Learn these nouns; the whole system is built from them.

- **Project** — a directory containing a `cairn.toml`, sources, prompts, and (generated)
  outputs. The unit of versioning. One project = one git repo (typically).
- **Source** — an input file or set of files. Read but never modified by Cairn.
- **Prompt** — a reusable Jinja2 template with variables and a small front-matter header.
- **Step** — the fundamental build unit. *Take these inputs, render this prompt over them,
  call this model/agent with these params, produce these outputs.* Analogue of a dbt model
  or a Bazel action. A step has a **kind**: `chat` (a model completion), `agent` (an
  autonomous agent run), or is marked `dynamic` (emits child work at runtime, §12.7).
- **`ref()` / `source()`** — functions usable inside input declarations and prompt
  templates. They build the DAG.
- **Map vs. Reduce** — fan-out (one output per input item) vs. fan-in (one output over all
  inputs). These are also the *parallel* multi-agent pattern at the graph level.
- **Materialization** — how a step's output is treated: `cached` (default: realize once,
  reuse until inputs change), `volatile` (re-run every build), `ephemeral` (computed, not
  persisted, inlined downstream).
- **Agent node** — a step with `kind = "agent"`: an LLM-in-a-loop with tools and a budget,
  possibly delegating to sub-agents. Opaque to the build graph; its realized **trajectory**
  is pinned and content-addressed like any other output (§12).
- **Tool** — a capability an agent node may use, provided via **MCP**. Classified `pure`
  (read-only) or `effectful` (mutates the world). Drives caching safety (§12.5).
- **Sub-agent** — an agent invoked by another agent (delegation). Its trajectory nests
  inside the parent's trajectory in provenance.
- **Trajectory** — the full recorded sequence of an agent run: reasoning steps, tool calls
  (args + results), sub-agent delegations. The agent analogue of an "output."
- **Manifest** — the runtime-emitted list of child work items from a `dynamic` step. Itself
  a pinned, content-addressed artifact (§12.7).
- **Budget** — hard caps on an agent node: max tokens, max iterations, max wall-clock.
  Enforced by Cairn to prevent runaways.
- **Agent Card / A2A backend** — the capability descriptor of an external agent Cairn can
  delegate to over A2A (§12.8).
- **Artifact** — a persisted output blob, stored content-addressed in the CAS.
- **Run** — one invocation of `cairn build`. Recorded in the **Ledger**.
- **Ledger** — append-only record (SQLite + per-run `run.json`) of every run: input
  hashes, output hashes, model, params, tools, trajectories, token counts, cost, times.
- **Action Cache (AC)** — maps a node's **action key** → the **content hash** of its
  realized output/trajectory.
- **Content-Addressable Store (CAS)** — maps a content hash → the blob.
- **Provenance Bundle** — the shareable compiled artifact: a self-contained static site
  showing every output and its full lineage, including recursive agent trajectories.

---

## 6. The Project Format (the on-disk convention)

This is the load-bearing invention. It must be minimal, readable, and obvious.

### 6.1 Directory layout

```
my-project/
├── cairn.toml              # project config + step definitions
├── inputs/                 # your sources (read-only to Cairn)
├── prompts/                # reusable prompt templates (Jinja2)
├── agents/                 # (optional) agent policies/system prompts + tool decls
├── outputs/                # GENERATED — human-readable results
│   └── bundle/             #   GENERATED — the shareable provenance bundle
└── .cairn/                 # GENERATED — internal state (git-ignored)
    ├── cache/              #   CAS: blobs by hash
    ├── ledger.db           #   SQLite run ledger
    └── runs/               #   one run.json per build
```

Rules: `inputs/`, `prompts/`, `agents/` are authored by humans. `outputs/` and `.cairn/`
are generated. Commit `outputs/` (so diffs show in PRs); never commit `.cairn/cache`.

### 6.2 `cairn.toml` (chat steps)

```toml
[project]
name = "research-synthesis"
version = "0.1.0"

[defaults]
model  = "claude-sonnet-4-6"
params = { temperature = 0.0, max_tokens = 4000 }

[sources.notes]
include = ["inputs/notes/**/*.md"]

[sources.spec]
include = ["inputs/spec.md"]

# MAP: one summary per note file.
[steps.summaries]
prompt          = "prompts/summarize.md"
over            = "source('notes')"
output          = "outputs/summaries/{{ item.stem }}.md"
materialization = "cached"

# REDUCE: one synthesis across all summaries.
[steps.synthesis]
prompt          = "prompts/synthesize.md"
inputs          = ["ref('summaries')", "source('spec')"]
output          = "outputs/synthesis.md"
materialization = "cached"
```

The DAG is **inferred** from `over` / `inputs`. (Agent and dynamic steps are in §12.)

### 6.3 A prompt template (`prompts/summarize.md`)

```markdown
---
description: Summarize a single source document into 5 bullet points.
---
You are a precise research assistant. Summarize the document below into at most
five bullet points, preserving any numbers and named entities verbatim.

<document path="{{ item.path }}">
{{ item.content }}
</document>
```

Templating is Jinja2. Variables: `item` (map steps), `source(name)`, `ref(step)`, plus
project `vars`. Binding rules are specified in §20.2.

---

## 7. Worked Example (end to end, in plain English)

1. `cairn init` scaffolds the layout.
2. You drop 20 transcripts in `inputs/notes/` and write the prompts.
3. `cairn build` parses config + prompts, builds the DAG, computes an action key per node,
   shows a plan and a **cost estimate**, you confirm, and it executes in dependency order,
   storing outputs in the CAS, writing readable files to `outputs/`, recording the run.
4. You edit a prompt. `cairn status` reports exactly which nodes are stale and the cost to
   rebuild. `cairn build` recomputes only those.
5. `cairn diff` shows how outputs changed. `cairn render` produces `outputs/bundle/` — a
   self-contained site where clicking any output reveals its full lineage. You send the
   folder to a collaborator who has never installed Cairn; they can audit every step.

That experience — `make` for a corpus of prompts, ending in a shareable provenance
artifact — is the whole product. §12 extends it to agents without changing the feel.

---

## 8. Architecture

### 8.1 Component overview

```
   cairn.toml ──┐        ┌──────────────────────────────────────┐
   prompts/   ──┼──────► │   Parser+Loader → DAG Builder →        │
   inputs/    ──┘        │   Planner (hash/diff/cost) →           │
   agents/    ──────────►│   Executor (scheduler) →               │
                         │     ├─ Provider Adapter → model API     │
                         │     ├─ Agent Backend → MCP tools / A2A   │
                         │     └─ Cache (AC + CAS)                  │
                         │   → Ledger + Renderer → outputs/, bundle/│
                         └──────────────────────────────────────┘
```

### 8.2 Components

- **Parser + Loader** — reads/validates `cairn.toml`, loads prompts + agent policies,
  resolves source globs. Pure, side-effect-free. Produces a typed `Project`.
- **DAG Builder** — resolves `over`/`inputs`/`ref()`/`source()` into a node graph (map
  steps expand per item; dynamic steps create a placeholder resolved at runtime). Detects
  cycles, missing refs, dangling outputs.
- **Planner** — computes each node's **action key** (§9), checks the AC, classifies nodes
  as `cached-hit` / `stale` / `new`, and produces a **work list** + **cost estimate**.
  Pure and unit-testable with a mocked cache.
- **Executor / Scheduler** — runs the work list in topological order with bounded
  concurrency, retries, rate-limit handling, a global cost ceiling, and per-agent budget
  enforcement. Calls Provider Adapters and Agent Backends. Writes to CAS + Ledger.
- **Provider Adapter** — thin interface wrapping each *model* backend (the only place that
  talks to a completion API). Swappable; testable via a `RecordedProvider` (§15).
- **Agent Backend** — thin interface wrapping each *agent* runtime: built-in loop, an
  external A2A agent, or a wrapped local runtime (LangGraph/CrewAI/CLI). Hosts MCP tools.
  Testable via a `RecordedAgent` that replays a captured trajectory (§15).
- **Cache** — Action Cache (key→hash) + CAS (hash→blob) on the local filesystem.
- **Ledger** — SQLite + per-run `run.json`. The provenance backbone.
- **Renderer** — reads Ledger + CAS, emits the Provenance Bundle (static site), including
  recursive trajectory views for agent nodes.

### 8.3 The adapter interfaces (stable contracts)

```python
class Provider(Protocol):                  # model completions
    name: str
    def complete(self, request: CompletionRequest) -> CompletionResult: ...
    def estimate_tokens(self, request: CompletionRequest) -> int: ...

class AgentBackend(Protocol):              # autonomous agent runs
    name: str
    def run(self, task: AgentTask) -> AgentResult: ...   # returns outputs + full trajectory
    def estimate(self, task: AgentTask) -> CostEstimate: ...

@dataclass(frozen=True)
class AgentTask:
    goal: str                      # rendered instruction/policy
    inputs: list[InputRef]         # files/refs the agent may read
    tools: list[ToolSpec]          # MCP tool specs (id + version + purity)
    sub_agents: list[AgentSpec]    # delegation targets
    model: str
    params: dict
    budget: Budget                 # max_tokens / max_iterations / max_seconds

@dataclass(frozen=True)
class AgentResult:
    outputs: dict[str, bytes]      # produced/changed files keyed by path
    trajectory: Trajectory         # full recorded run (for cache + provenance)
    input_tokens: int
    output_tokens: int
```

Built-in adapters in v1: a generic **HTTP chat** Provider; in later phases a **built-in
agent loop** AgentBackend, an **A2A** AgentBackend, and a **CLI-agent** AgentBackend.
New backends implement the Protocol — nothing else changes.

---

## 9. The Cache-Key Algorithm (specified precisely)

This is the heart. Get it exactly right.

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

**Side-effect safety (agent-specific, see §12.5):** an agent node whose tools are all
`pure` is safe to cache. An agent node with any `effectful` tool may **not** be silently
served from cache (replaying wouldn't re-perform the side effect); it must be declared
`volatile`, or the user must explicitly accept caching with a loud warning.

**Why this is correct:** the key captures *every* input that could change the output
(prompt/policy, model, params, tools, sub-agents, budget, and the transitive closure of
input bytes). Anything not in the key must not affect the output — the hermeticity
contract, made true by pinning.

---

## 10. Command Surface (the CLI)

Small, predictable, composable. Every command is safe to run repeatedly.

| Command | What it does |
|---|---|
| `cairn init [dir]` | Scaffold a new project (layout + example). |
| `cairn validate` | Parse + type-check config, prompts, agent/tool decls; resolve the DAG. **Spends no tokens.** Runs in CI. |
| `cairn doctor` | Preflight environment check (no tokens): resolved provider credentials present, base URLs/models recognized, declared MCP servers reachable, declared CLI agents on PATH. Fail-loud before any spend (R18). |
| `cairn status` | Per-node `cached`/`stale`/`new` + total estimated cost (incl. agent budget ceilings). No tokens spent. |
| `cairn plan` | Like `status` but prints execution order and rendered prompts/policies. |
| `cairn build [selector]` | Execute the work list. `--dry-run`, `--refresh`, `--max-cost`, `--concurrency`, `--yes`. Confirms above a cost threshold. Enforces agent budgets. |
| `cairn diff [selector]` | Show how outputs/trajectories changed versus the previous run. |
| `cairn render [--out dir] [--zip]` | Build the Provenance Bundle (incl. recursive agent trajectory views). |
| `cairn trace <node>` | Print/inspect a single agent node's full trajectory (tools, sub-agents). |
| `cairn test` | Run declared assertions over outputs (§15). |
| `cairn cache (status\|gc\|clear)` | Inspect, GC, or clear the local cache. |
| `cairn run <prompt> [--input ...]` | One-off render+run outside the DAG. |
| `cairn docs` | Generate a static DAG/lineage view of the project. |

**Selectors** (dbt-style): `cairn build summaries`, `cairn build +critique` (upstream),
`cairn build summaries+` (downstream), `cairn build tag:report`.

---

## 11. Key Flows (step by step)

**Cold build.** `validate` → DAG → Planner marks all `new` → show plan + cost → confirm →
Executor runs level by level → CAS + Ledger → `outputs/` written.

**Incremental rebuild.** Edit a file/prompt → `status` recomputes keys → only changed keys
are `stale` → `build` runs just those → downstream keys change automatically → the cascade
halts where a regenerated output is byte-identical (content-addressing gives this for free).

**Diff.** `diff` reads the last two runs from the Ledger, fetches both blobs from the CAS,
renders unified diffs per output (and trajectory diffs for agent nodes).

**Render & share.** `render` walks the latest run, pulls every output and its lineage,
emits a self-contained static site (plain HTML + minimal vanilla JS). `--zip` for one file.

**Agentic flows** are specified in §12.

---

## 12. Agentic & Multi-Agent Workflows

This section extends Cairn to autonomous and multi-agent work **without** turning it into
an agent runtime or an orchestration framework.

### 12.1 Stance (read this first)

Cairn is the **reproducible build substrate around agentic work**, not another
orchestrator. It *composes* agent runtimes (built-in loop, LangGraph, CrewAI, Claude Code,
or external A2A agents); it does not compete with them. Its contribution is exactly the
layer where agentic systems fail today: **reproducibility, provenance, caching, and cost
governance**.

Two honest constraints, grounded in the research, are baked into the design:

- **Most "agentic" work isn't.** If a unit of work is deterministic, it's a step, not an
  agent (Principle #11). Sequential chains and parallel fan-out/fan-in are expressed as
  ordinary steps/map-reduce — cached and cheap — and only genuinely autonomous work
  becomes an agent node.
- **Multi-agent is expensive.** It adds large token overhead and only pays off with real
  specialization, parallelism, or critique. Cairn surfaces estimated multi-agent overhead
  and nudges toward plain steps.

### 12.2 The two-level model (the reconciliation)

Cairn separates two graphs:

- **Macro graph (static, content-addressed):** the build DAG of steps. Sequential = a
  chain of steps; parallel = map/reduce. These two of the five dominant multi-agent
  patterns require **no new machinery** — they're already cached at the graph level.
- **Micro execution (dynamic, non-deterministic):** what happens *inside* an agent node —
  the think→act→observe loop, tool calls, sub-agent delegation. This is **opaque** to the
  macro graph.

The bridge is §2's core move, extended: Cairn pins the **realized trajectory** of an agent
node, content-addressed by its inputs. A re-run with unchanged inputs **replays** the
pinned trajectory (zero tokens, zero tool calls); `--refresh` re-rolls.

### 12.3 The agent node

```toml
[steps.researcher]
kind     = "agent"
policy   = "agents/researcher.md"     # system prompt / instructions (Jinja2)
inputs   = ["source('brief')"]
output   = "outputs/research/{{ item.stem }}.md"   # or a directory for multi-file output
model    = "claude-opus-4-8"
params   = { temperature = 0.2 }
tools    = ["mcp:websearch@1", "mcp:filesystem:read@1"]   # all pure → cacheable
effects  = "pure"                     # "pure" | "effectful"
budget   = { max_tokens = 200000, max_iterations = 30, max_seconds = 600 }
backend  = "builtin"                  # "builtin" | "a2a:<url>" | "cli:<cmd>" | "langgraph:<entry>"
```

The agent runs to completion within its budget; Cairn captures `(outputs, trajectory)` as
the node's pinned, content-addressed result.

### 12.4 Tools via MCP

Agent nodes receive capabilities through **MCP**, the vendor-neutral tool standard.
Cairn acts as an **MCP host** for the duration of an agent node, exposing only the
declared tools. Tool **ids + versions are part of the cache key** (§9), because changing an
agent's tools can change its output. Tools are declared with a **purity** (`pure` vs
`effectful`).

### 12.5 Side effects & caching safety (the part frameworks get wrong)

- **Pure-only agent nodes** (`effects = "pure"`): safe to `cache`. Replaying the pinned
  trajectory is sound, because nothing in the world was mutated.
- **Effectful agent nodes** (`effects = "effectful"`): a cached replay does **not**
  re-perform the side effect. Cairn therefore refuses to silently cache them — you must set
  `materialization = "volatile"` (always re-run) or explicitly opt into caching, and Cairn
  emits a loud warning at `validate`/`plan` time. This is a deliberate safety stance
  consistent with Principle #8 (fail loud).

### 12.6 The five patterns, mapped to Cairn

| Pattern | How Cairn expresses it | Where it lives |
|---|---|---|
| **Sequential / chain** | A chain of steps via `ref()`. | Macro graph (cached). |
| **Parallel fan-out/fan-in** | `map` step + `reduce` step. | Macro graph (cached). |
| **Orchestrator-worker / hierarchical** | A `dynamic` agent step that emits a runtime manifest of worker items → a map over those items → a reduce (§12.7). | Macro graph, resolved at runtime (cached per item). |
| **Handoff / routing** | A step outputs a routing decision (data); downstream steps carry a `when` predicate over it, or the route selects manifest items. | Macro graph. |
| **Loop / critic-refiner (evaluator-optimizer)** | Preferred: a bounded sub-graph `generate → critique → revise` with `max_rounds` (each round cached + inspectable). Alternative: an opaque agent loop inside one node. Hard caps always enforced. | Either level. |

### 12.7 Dynamic steps (runtime-determined DAG — the hard, valuable bit)

An orchestrator can't always know its workers ahead of time ("research each subtopic I
discover"). A `dynamic` step solves this:

```toml
[steps.plan]
kind    = "agent"
dynamic = true                       # emits a manifest instead of a single output
policy  = "agents/planner.md"
inputs  = ["source('brief')"]
emits   = "workers"                  # name of the child work-set this step produces
budget  = { max_iterations = 10 }

[steps.work]
kind   = "agent"
over   = "manifest('workers')"       # fan-out over the runtime-emitted items
policy = "agents/worker.md"
output = "outputs/work/{{ item.id }}.md"

[steps.report]
prompt = "prompts/report.md"
inputs = ["ref('work')"]
output = "outputs/report.md"
```

Mechanics: `plan` runs and emits a **manifest** (a JSON list of items, each with an `id`
and its own inputs/params). Cairn content-addresses the manifest, then materializes each
`work` item as a normal cached node. On rebuild: an unchanged manifest ⇒ children served
from cache; a changed manifest ⇒ Cairn diffs it, runs only new/changed children, and
prunes outputs of removed children. This is the Dagster-dynamic-output / Airflow
dynamic-task-mapping idea, adapted so **caching survives the dynamic boundary** — which is
the part nobody packages.

### 12.8 External & heterogeneous agents via A2A

An agent node can be backed by an **external A2A agent** (`backend = "a2a:<url>"`). Cairn
reads the agent's **Agent Card**, delegates the task over A2A, and captures the result and
trajectory as the node's pinned output. This lets Cairn orchestrate multi-vendor / remote
agents at the macro-graph level while keeping its caching and provenance guarantees. Cairn
speaks A2A **as a client/orchestrator only** — it never implements an agent runtime. A
local runtime (LangGraph/CrewAI/Claude Code) is wrapped the same way via a CLI or library
adapter behind the `AgentBackend` Protocol (§8.3).

### 12.9 Provenance for agents (the differentiator)

For an agent node, the Provenance Bundle renders the **full, recursive trajectory**: each
reasoning step, each tool call (name, arguments, result), and each sub-agent delegation
(expandable into the sub-agent's own trajectory). Because the whole trajectory is pinned
and content-addressed, the result is a **reproducible, offline-auditable, shareable
multi-agent run** — something existing agent frameworks do not package, and a direct
answer to the observability/debugging pain that sinks agentic pilots.

### 12.10 Cost & safety governance

- Every agent node **must** declare a `budget` (max tokens / iterations / wall-clock).
  Cairn enforces hard caps — this is the primary defense against infinite loops and
  runaway cost.
- `cairn status`/`plan` show worst-case agent cost (budget ceilings) alongside cached
  savings. `--max-cost` sets a global ceiling for the whole build.
- Cairn flags multi-agent steps with an estimated overhead note and suggests a plain-step
  alternative where an agent isn't warranted (Principle #11).

### 12.11 What this is explicitly NOT

Cairn does **not** replace LangGraph, CrewAI, AutoGen, ADK, or Claude Code; it does not
introduce a new orchestration DSL competing with A2A; it does not run long-lived,
always-on agents (builds are batch and reproducible). It **wraps and composes** these
systems to add the reproducibility/provenance/caching layer. See §19 (Non-Goals).

---

## 13. Tech Stack & Rationale

| Concern | Choice | Why |
|---|---|---|
| **Language (core)** | **Python 3.11+** | The LLM/agent ecosystem (provider SDKs, MCP SDK, A2A SDK, tokenizers, Jinja2) lives here; dbt proved Python scales to a massive OSS CLI; lowest barrier for contributors. The hot path is network I/O, not CPU. |
| **Distribution** | `uv`/`pipx` + standalone binaries (PyInstaller) per-OS | Honors zero-infra: `uvx cairn` or a single downloaded binary. |
| **CLI framework** | Typer (Click) + Rich | Typed commands, great help, pretty output. |
| **Config** | TOML (`tomllib`) + Pydantic schema | Readable, typed, validated with clear errors. |
| **Templating** | Jinja2 (sandboxed) | Battle-tested; same choice as dbt/promptfoo. |
| **Hashing** | `hashlib.sha256` over canonical JSON | Boring, correct, fast enough. |
| **Cache/Ledger** | Filesystem CAS + SQLite | Zero-infra, transactional, git-diffable run files. |
| **Concurrency** | `asyncio` + bounded semaphore | Natural fit for parallel API/tool calls. |
| **Tools** | **MCP** (official SDK) | Vendor-neutral, Linux-Foundation-governed standard. |
| **External agents** | **A2A** (official SDK) | Vendor-neutral agent-to-agent standard. |
| **Renderer** | Static HTML + vanilla JS | Self-contained, no build step, opens offline. |
| **Testing** | pytest + syrupy + `RecordedProvider`/`RecordedAgent` | Deterministic tests for a non-deterministic domain (§15). |

**The one debate to flag:** a single static binary favors Go/Rust. We choose Python anyway
for ecosystem + contributor reach (the dbt precedent) and solve distribution with bundled
binaries. **Do not** start in Rust "for performance" — network latency, not CPU, is the
bottleneck, and Rust shrinks the contributor pool.

---

## 14. Coding Guidelines & Conventions

The codebase must stay readable enough that a newcomer can land a PR in a weekend.

```
cairn/
├── cli/        # Typer commands; thin, no logic
├── model/      # Project, Step, Node, AgentTask, Trajectory dataclasses (pure data)
├── loader/     # config + prompt + agent/tool loading & validation
├── graph/      # DAG building, dynamic-step resolution, cycle detection, selectors
├── plan/       # hashing, cache resolution, cost/budget estimation
├── cache/      # AC + CAS
├── ledger/     # SQLite + run.json
├── providers/  # model adapters (http, recorded)
├── agents/     # agent backends (builtin loop, a2a, cli, recorded) + MCP host
├── execute/    # scheduler/executor + budget enforcement
├── render/     # provenance bundle (incl. trajectory views)
└── util/       # tiny shared helpers
```

**Rules**

1. **Pure core, thin shell.** Logic lives in `loader/`, `graph/`, `plan/`. `cli/`,
   `execute/`, `providers/`, `agents/` only orchestrate. The Planner must be a pure
   function of `(Project, CacheView)`.
2. **Types everywhere.** Full hints; `mypy --strict` in CI; Pydantic at boundaries.
3. **One module, one responsibility.** If you can't describe it in one sentence, split it.
4. **Errors are values with context.** Name the file, the line, what was expected, the fix.
   No bare tracebacks reach users.
5. **No hidden global state.** Cache, ledger, MCP host are injected, not imported.
6. **Determinism is a test target.** Any function feeding an action key has a golden-hash
   test that fails on unexpected change.
7. **Formatting/linting:** `ruff` + `mypy` pre-commit and in CI. Zero-config for contributors.
8. **Commits & PRs:** Conventional Commits; tests required; docs updated in the same PR
   (docs-as-code). SemVer; the action-key format and `cairn.toml` schema are public
   contracts with their own versions.
9. **Dependencies are a liability.** Adding one requires justifying why it can't be vendored.
10. **Public API stability:** the schema, the CLI surface, the action-key algorithm, and
    the MCP/A2A integration points are versioned contracts; breaking them needs a major
    version + migration note.

---

## 15. Testing & Validation Strategy

Testing a non-deterministic tool: make the non-determinism injectable and recorded.

- **Unit tests (the bulk).** Parser, DAG builder, dynamic-step resolution, selectors, and
  especially the **Planner and hashing** are pure and fully unit-tested. Golden-hash tests
  assert exact action keys for fixed inputs (incl. agent tool sets).
- **`RecordedProvider` / `RecordedAgent` (record/replay).** Record mode calls a real
  model/agent once and saves the response/trajectory as a fixture; replay mode (CI default)
  serves the fixture. Deterministic, offline, free end-to-end tests of build/diff/render
  and full agent trajectories without burning tokens — the VCR pattern adapted to LLMs and
  agents.
- **Snapshot tests.** Rendered bundle (incl. trajectory views) and CLI output snapshotted.
- **Property tests (the soul).** "Building twice with no changes spends zero tokens and
  zero tool calls." "Editing one of N map inputs invalidates exactly one output." "An
  unchanged regenerated output halts the downstream cascade." "An unchanged dynamic manifest
  serves all children from cache." "An effectful agent node is never silently cached."
- **End-to-end fixtures.** Example projects (research synthesis, doc generation, code
  analysis, an orchestrator-worker research agent) run in CI under replay; they double as
  documentation.
- **The real-world validation gate (most important).** Automated tests prove correctness,
  not desire. Each phase below ships to N real users in one niche and watches whether they
  adopt a free tool. If they don't, stop and rethink.

---

## 16. Phase-by-Phase Build Plan

Each phase has **goal**, **deliverables**, **exit criteria (technical)**, and a
**validation gate (human)**. Don't start a phase before the previous gate passes.

### Phase 0 — Spike & decide (1 week)
- **Goal:** de-risk the core idea.
- **Deliverables:** a throwaway script running a 3-node DAG (map + reduce + single) with
  content-addressed caching against one real provider.
- **Exit:** "edit one input → only the affected node re-runs" works once, by hand.
- **Validation gate:** *you* feel the "whoa" on one of your own real tasks. If not, stop.

### Phase 1 — Core build engine (3–4 weeks)
- **Goal:** the minimum tool genuinely useful to its author.
- **Deliverables:** `init`/`validate`/`doctor`/`status`/`plan`/`build`; TOML schema; Jinja
  rendering; map+reduce+single chat steps; AC+CAS; cost estimator; HTTP Provider;
  the **provider capability registry** (R18.1), **credential resolver** (R18.2, zero-config for
  standard env vars), and **per-provider retry policy tables** (R18.3); `RecordedProvider`; full
  unit/property/golden-hash tests.
- **Exit:** §4 principles hold; building twice spends zero tokens; one-file edits
  invalidate exactly the right nodes; `cairn doctor` catches a missing key/model before spend;
  `mypy --strict` + `ruff` clean.
- **Validation gate:** *you* run all your real corpus tasks through it for two weeks and
  stop using the manual/script way.

### Phase 2 — Provenance & sharing (2–3 weeks)
- **Goal:** the differentiator that makes people share it.
- **Deliverables:** Ledger; `render` (self-contained provenance bundle); `--zip`.
- **Exit:** a non-user opens the bundle offline and traces any output to its inputs +
  prompt + model + params.
- **Validation gate:** hand a bundle to **5 people in one niche**; two unprompted installs
  = a real signal.

### Phase 3 — Iteration ergonomics (2 weeks)
- **Goal:** delightful daily iteration (retention).
- **Deliverables:** `diff`, selectors, `--refresh`, `--max-cost`, `samples = n`, `docs`.
- **Exit:** edit → status → build → diff is fast and obvious.
- **Validation gate:** ≥3 external people use it **weekly**, unprompted.

### Phase 4 — Agent nodes & tools (3–4 weeks)
- **Goal:** single-agent autonomy with full reproducibility (satisfies "general-purpose
  coding agents, not just chat").
- **Deliverables:** `kind = "agent"`; built-in agent loop; **MCP host** + tool purity;
  budget enforcement; side-effect safety (§12.5); CLI-agent backend via the **agent profile
  registry** (R18.4 — named backends like `claude-code`/`codex` plus the `cli:<cmd>` escape
  hatch, invocation-only, no config mutation); `cairn doctor` extended to check agent binaries;
  trajectory capture; trajectory views in the bundle; `cairn trace`; `RecordedAgent`.
- **Exit:** an agent node caches, replays, diffs, and renders identically to a chat step; an
  effectful agent is never silently cached; budgets are hard-enforced.
- **Validation gate:** at least one external user runs an agent node over their own files and
  shares the resulting trajectory bundle.

### Phase 5 — Multi-agent & interop (3–4 weeks)
- **Goal:** orchestrator-worker, hierarchical, handoff, and loop patterns + heterogeneous
  agents.
- **Deliverables:** `dynamic` steps + runtime manifests + caching across the dynamic
  boundary (§12.7); `manifest()`/`when` predicates; **A2A** backend (external agents);
  recursive sub-agent trajectories in provenance; an example orchestrator-worker research
  agent; optional Dagster execution backend for heavy users; documented plugin point for
  new Providers/AgentBackends.
- **Exit:** an unchanged manifest serves all children from cache; an external A2A agent
  caches/renders like a built-in one; a third-party backend can be added without touching
  core.
- **Validation gate:** one external contributor lands a backend/plugin PR; one user runs a
  real multi-agent workflow and audits it via the bundle.

### Phase 6 — Polish, docs, community (ongoing)
- **Deliverables:** bundled per-OS binaries; docs site with a 5-minute quickstart + worked
  examples (chat and agentic); published schema for editor autocomplete; contribution guide;
  release automation.
- **Exit:** newcomer goes install → first rendered bundle in under 10 minutes from docs alone.
- **Validation gate:** §18 success metrics trend up over two consecutive releases.

---

## 17. Risks & Mitigations (the honest list)

- **"Feature, not a tool."** *Mitigation:* the provenance bundle (Phase 2) is the
  irreducible differentiator; lead with it. If Phase 2's gate fails, the thesis is wrong.
- **Big labs move context management upstream.** *Mitigation:* Cairn's durable value is
  reproducibility/provenance over a corpus and over agent runs — which models managing their
  own context do not provide. Anchor messaging there.
- **Non-determinism / side-effects confuse users.** *Mitigation:* `status`/`diff` make
  staleness explicit; `--refresh` is discoverable; effectful agents fail loud; docs explain
  pinning and purity in one example each.
- **Multi-agent cost blowups & infinite loops.** *Mitigation:* mandatory per-agent budgets,
  hard caps, global `--max-cost`, worst-case cost shown before running, and a nudge toward
  plain steps (Principle #11).
- **Scope creep into an orchestration framework.** The strongest gravity. *Mitigation:* §12.11
  and §19 are load-bearing; Cairn *wraps* runtimes (MCP/A2A/CLI backends), never reimplements
  them. Reject PRs that add an in-house orchestration DSL or a long-lived agent runtime.
- **Protocol churn (MCP/A2A still evolving).** *Mitigation:* isolate behind the
  Provider/AgentBackend Protocols and the MCP host module; pin SDK versions; treat protocol
  integration as a versioned contract.
- **Narrow audience (terminal power users).** True. *Mitigation:* that audience is real,
  reachable, and adopts free tools. Aim for a few thousand people who love it.

---

## 18. Success Metrics (for a tool people love, not a startup)

Stars are vanity. Track: **weekly-active self-hosters**; unprompted "I use this daily/weekly"
testimonials from non-authors; **external contributors** landing non-trivial PRs;
**projects in the wild** (public repos with a `cairn.toml`); **bundles shared** (the truest
signal — the artifact is the growth loop); and, for agentic adoption, **agent trajectory
bundles shared**. North star: *would the median user be annoyed if Cairn disappeared
tomorrow?*

---

## 19. Non-Goals (say no to these forever, in the core)

- Not an **evaluation/benchmarking platform** (compose with promptfoo/Braintrust).
- Not a **hosted SaaS**, account system, or billing.
- Not a **real-time collaborative editor** (git is the collaboration layer).
- Not a **vector database / RAG framework** (compose with one).
- Not an **agent runtime or orchestration framework.** Cairn *invokes and composes* agents
  (built-in loop, MCP tools, A2A, CLI/LangGraph/CrewAI backends) to add reproducibility,
  provenance, and caching. It does not run long-lived agents, and it does not introduce an
  in-house orchestration DSL competing with A2A.
- Not a **notebook** (no live kernel; builds are batch and reproducible).
- Not a **GUI** in the core (the provenance bundle is read-only output, not an app).

Any of these may exist *around* Cairn as separate, optional projects. None may enter core.

---

## 20. Appendix

### 20.1 Glossary

*Action key* — the SHA-256 fingerprint of everything that determines a node's output.
*CAS* — content-addressable store (hash → bytes). *AC* — action cache (key → hash).
*Map/Reduce* — fan-out vs fan-in. *Materialization* — how an output is persisted/cached.
*Ledger* — the run-by-run provenance record. *Bundle* — the shareable provenance artifact.
*Pinning* — fixing a non-deterministic output/trajectory so the same key always yields the
same bytes. *Agent node* — an autonomous LLM-in-a-loop step. *Trajectory* — an agent run's
full recorded sequence. *Manifest* — a dynamic step's runtime-emitted child work-set.
*Budget* — hard caps on an agent node. *MCP* — agent↔tool protocol. *A2A* — agent↔agent
protocol. *Agent Card* — an A2A agent's capability descriptor.

### 20.2 Template variable binding rules

- In a **map** step: `item` is bound per input file with `.path`, `.name`, `.stem`,
  `.content`; the step runs once per item (each item is its own cache node).
- `source(name)` returns that source set's content (or a list when iterated).
- `ref(step)` returns the upstream output: a single object for single/reduce steps, a list
  for map steps.
- `manifest(name)` (dynamic steps) returns the runtime-emitted child items; each item has an
  `id` plus its declared inputs.
- Project-level `vars` are global. Templates render in a Jinja sandbox; no code execution.

### 20.3 `cairn.toml` schema (informal)

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

> **Cairn turns a folder of files, prompts, and agents into reproducible, shareable
> artifacts — recomputing only what changed and pinning every completion and agent
> trajectory — a build system for LLM work.**

---

*End of charter. If you build exactly what's written here, you've built Cairn. If you're
tempted to add something not written here, check it against §4 (Principles), §12.11, and
§19 (Non-Goals) first — especially anything that smells like an agent runtime.*

---
---

# PART II — Detailed Engineering Reference (R1–R17)

> **No-ambiguity implementation spec.** Part I (§1–§20) gives the design, contracts, and
> principles. Part II specifies exact formats, algorithms, protocols, and edge cases so the
> tool can be built without further design decisions. **If Part I and Part II ever conflict,
> Part I's principles (§4) win — record the conflict as an ADR and surface it.**

All identifiers, field names, and file paths below are normative. JSON examples are
illustrative of structure, not exhaustive.

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
├── runs/<run_id>.json   # human-readable per-run mirror (git-diffable provenance)
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

## R7. Trajectory data model (canonical JSON)

```
Trajectory = {
  version, node_id, model, params, started_at, ended_at,
  status: "completed" | "budget_exhausted" | "failed",
  usage: { input_tokens, output_tokens },
  events: [ Event, ... ]
}
Event =
  | { type:"message",     role, content:[ContentBlock] }
  | { type:"tool_call",   tool_id, name, args, started_at }
  | { type:"tool_result", tool_id, result_hash, is_error, ended_at, duration_ms }
  | { type:"sub_agent",   agent_ref, trajectory_hash, status }   # nested, recursive
  | { type:"budget_check",iter, tokens, elapsed_s }
  | { type:"error",       message, fatal }
```

- The trajectory is one CAS blob. **Large tool results and sub-agent trajectories are stored
  as separate CAS blobs referenced by hash** (`result_hash`, `trajectory_hash`) to dedupe and
  to make provenance recursive.
- The trajectory hash participates in `ref()` resolution exactly like a normal output hash, so
  a downstream step depending on an agent node invalidates correctly when the trajectory
  changes.

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

## R14. The Ledger — SQLite schema (DDL) + run.json

```sql
PRAGMA user_version = 1;   -- schema_version; migrations applied on open, never destructive

CREATE TABLE runs (
  run_id TEXT PRIMARY KEY, started_at TEXT, ended_at TEXT, status TEXT,
  total_cost REAL, total_input_tokens INTEGER, total_output_tokens INTEGER,
  cairn_version TEXT, key_version INTEGER, git_commit TEXT
);
CREATE TABLE nodes (
  run_id TEXT, node_id TEXT, step TEXT, item_id TEXT, kind TEXT,
  action_key TEXT, output_hash TEXT, status TEXT, model TEXT, params_json TEXT,
  input_tokens INTEGER, output_tokens INTEGER, cost REAL, duration_ms INTEGER,
  started_at TEXT, ended_at TEXT,
  PRIMARY KEY (run_id, node_id)
);
CREATE TABLE action_cache (            -- the AC
  action_key TEXT PRIMARY KEY, output_hash TEXT, kind TEXT,
  created_at TEXT, last_used_at TEXT, model TEXT
);
CREATE TABLE tool_calls (              -- agent provenance / queryability
  run_id TEXT, node_id TEXT, seq INTEGER, tool_id TEXT, name TEXT,
  args_hash TEXT, result_hash TEXT, is_error INTEGER, duration_ms INTEGER
);
CREATE TABLE cas_refs (                -- gc roots
  output_hash TEXT, run_id TEXT, node_id TEXT
);
```

- **`runs/<run_id>.json`** is a human-readable mirror of one run (nodes + summary) for
  git-diffable provenance and as the data source for `render`.
- **Migrations:** keyed on `PRAGMA user_version`; applied on open; back up `ledger.db` before
  any non-trivial migration.

## R15. The Provenance Bundle — structure & rendering

```
outputs/bundle/
├── index.html      # self-contained: embeds ALL run + lineage + trajectory data
├── assets/         # one css, one js — NO framework, NO build step
└── (optional) data/  # only used when --split is passed; default is fully inlined
```

- **Self-contained by default:** all data is embedded in `index.html` inside
  `<script type="application/json" id="cairn-data">…</script>`, so the file opens via `file://`
  with no server and no network (avoids browser `fetch` restrictions on `file://`). `--zip`
  packages the directory; `--split` writes external `data/` for very large bundles.
- **Lineage drill-down:** every output links to its inputs (source paths + hashes, upstream
  refs), the full prompt text, model, and params. **Agent nodes** render the recursive
  trajectory: collapsible events, tool calls with args/results, and nested sub-agent
  trajectories (resolved from their CAS hashes, inlined at render time).
- Rendering is plain DOM manipulation over the embedded JSON. No localStorage/sessionStorage.

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

## R17. Invariants & edge-case checklist (must all hold; each gets a test)

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

---

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

---

*End of Part II. Between Part I and Part II, every component of Cairn is specified end to end:
the format, the engine, the providers, the agents, MCP/A2A interop, the executor, the cache,
the ledger, and the shareable bundle. Build from this; deviate from nothing; when genuinely
ambiguous, prefer Part I's principles (§4) and §19's non-goals, write an ADR, and ask.*