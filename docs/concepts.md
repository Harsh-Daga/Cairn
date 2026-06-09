# Concepts

This page explains how Cairn models inference work. You do not need to read source code to use
the product.

## The problem Cairn solves

When you use coding agents and LLM APIs, you get fragments: JSONL logs, chat exports, git diffs,
and ad-hoc notes. Cairn reconstructs a **single causal story** — what context was used, what
tools ran, what files changed, and what was produced.

## Core ideas

### Everything is a directed graph

```
Context → Prompt / Workflow → Execution → Tool calls → Artifacts → Report
```

Cairn infers or declares this graph, stores it in an append-only ledger, and renders it as
turn cards, timelines, and DAG views.

### Local-first storage

Each project has a `.cairn/` directory:

| Path | Purpose |
|------|---------|
| `ledger.db` | Append-only SQLite — sessions, events, runs, lineage |
| `cache/cas/` | Content-addressed blobs (SHA-256) for prompts, outputs, snapshots |
| `watch/` | Ingest cursors and hook install state |

No cloud account is required. Delete Cairn and you still keep your repo and git history.

### Two execution paths, one report

| Path | How it starts | Typical use |
|------|---------------|-------------|
| **Capture** | `cairn ingest` | Record what Claude Code, Cursor, or another agent did |
| **Pipeline** | `cairn build` | Run a declared workflow over your files with an LLM provider |

Both produce the same bundle shape: summary, narrative, tool usage, artifact inventory,
execution graph, and reproducibility metadata. Reports are scrubbed for common secret patterns
before export.

### Projects and configuration

A **project** is a directory (usually your git repo) scoped to Cairn.

- `cairn init` scaffolds `cairn.toml`, prompts, and example inputs.
- `cairn.toml` is optional for capture-only use — `cairn ingest` works without it.
- **Context assets** are files Cairn indexes (`cairn context scan`).
- **Workflows** are versioned step definitions (`cairn workflow list`).

### Sessions and runs

| Term | Meaning |
|------|---------|
| **Session** | One continuous agent conversation (capture path) |
| **Run** | One provider workflow execution (pipeline path) |
| **Event** | Normalized ledger row: message, tool_call, tool_result, file_snapshot, … |
| **Artifact** | Output or intermediate blob with lineage edges |

Use `cairn sessions list` for capture and `cairn runs` for provider builds.

### Content-addressed caching

Pipeline steps compute an **action key** from inputs (prompt hash, model, params, upstream
outputs). Identical keys skip LLM calls — safe, exact cache hits only.

Recorded provider mode (`--provider-mode recorded`) replays fixtures for CI with zero tokens.

### Bundles and offline reports

`cairn render` writes a **self-contained HTML bundle**:

- Works at `file://` with no network
- Embeds data as JSON inside the page (scrubbed)
- Includes CSS/JS assets inline or co-located

Zip with `--zip` for sharing. Encrypt with `cairn security encrypt` when needed.

### Live workspace

`cairn live serve` hosts session HTML and pushes updates over Server-Sent Events (SSE). Bind
address defaults to `127.0.0.1` — local only.

### Snapshots and collaboration

- **Snapshots** freeze project state for diff and restore (`cairn snapshot`).
- **Collab bundles** export/import ledger slices for file-based sync (`cairn collab`).

## Design principles (short)

1. **Capture fails open; build fails loud** — hooks never block agents; `validate`/`doctor` guard spend.
2. **Provenance is the product** — traceability beats polished but opaque output.
3. **No lock-in** — standard files, open formats, local storage.
4. **Boring technology** — Python, SQLite, SHA-256, vanilla JS.

## Next steps

- [Getting started](getting-started.md) — hands-on tutorial
- [CLI reference](cli.md) — command lookup
- [Security](security.md) — credentials and sharing
