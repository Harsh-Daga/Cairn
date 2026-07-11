<p align="center">
  <svg xmlns="http://www.w3.org/2000/svg" width="72" height="56" viewBox="0 0 72 56" role="img" aria-label="Cairn">
    <ellipse cx="36" cy="44" rx="28" ry="10" fill="#6b5a45"/>
    <ellipse cx="36" cy="32" rx="22" ry="9" fill="#8a7355"/>
    <ellipse cx="36" cy="22" rx="16" ry="7" fill="#a89070"/>
    <ellipse cx="36" cy="14" rx="10" ry="5" fill="#c4ad87"/>
  </svg>
</p>

<p align="center">
  <strong>Cairn watches what your AI coding agents actually do — profiles every token,<br>
  fingerprints behavior, ties it to real outcomes, and rewrites your instruction files<br>
  to fix the waste, then statistically proves the fix worked.</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/cairn-workspace/"><img src="https://img.shields.io/pypi/v/cairn-workspace.svg" alt="PyPI"></a>
  <a href="https://github.com/Harsh-Daga/Cairn/actions/workflows/ci.yml"><img src="https://github.com/Harsh-Daga/Cairn/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-blue.svg" alt="License"></a>
  <img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python">
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/docs/assets/hero.gif" width="720" alt="Cairn demo: Overview → session → replay scrub → blame toggle">
</p>

---

## 60-second quickstart

**Primary — uv tool**

```bash
uv tool install cairn-workspace
cd your-repo && cairn
```

**pip**

```bash
pip install cairn-workspace
cd your-repo && cairn
```

**curl installer**

```bash
curl -LsSf https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/scripts/install.sh | sh
cd your-repo && cairn
```

No account, no cloud, no config. `cairn stop` to quit.

### Or let your agent install it

Paste this into Claude Code, Cursor, Codex, or any coding agent. It fetches the full setup prompt and wires MCP automatically.

```
Set up Cairn (open-source agent observability, https://github.com/Harsh-Daga/Cairn) in this repo. Fetch https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md and follow it exactly. Do not use sudo; stop and report if any VERIFY step fails.
```

Full prompt: [AGENT_SETUP.md](AGENT_SETUP.md) · `cairn setup-prompt`

---

## The five pillars (+ causal traces)

**Context profiling** — Decompose each trace into regions (system, tool schema, tool results, retrieved files, user, history). Surface re-billing waste and concrete fixes: cache, clear stale results, drop unused tools.

**Behavioral fingerprinting** — Compress sessions into behavioral vectors. Detect drift with AMDM (Mahalanobis + per-axis EWMA). See when an agent's behavior changed and which axes moved.

**Outcome-anchored quality** — Capture git and test signals after sessions. Score process quality, not just pass/fail. Flag brittle "lucky pass" sessions.

**Measured self-improvement** — Propose instruction edits to `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`. Apply with human approval. Measure before/after on a holdout window with anytime-valid verdicts.

**Agent self-awareness (MCP)** — MCP tools mid-session: recurring waste, project primer, session-so-far, should-I-stop. Auto-install via Settings or `cairn mcp install`.

**Causal traces** — Parent/child spans, retry links, blame view for multi-agent failures. Waterfall swimlanes show handoffs and retry arcs.

---

## What it looks like

| Overview | Session waterfall + strata | Optimize verdict |
|----------|---------------------------|------------------|
| ![Overview](https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/docs/assets/overview.png) | ![Session detail](https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/docs/assets/session-detail.png) | ![Optimize verdict](https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/docs/assets/optimize-verdict.png) |

Live demo (Phase L7): GitHub Pages link coming soon.

---

## Supported agents

| Agent | Adapter ID | Log source |
|-------|------------|------------|
| Claude Code | `claude_code` | `~/.claude/projects/…/*.jsonl` |
| Codex CLI | `codex` | `~/.codex/sessions/…/*.jsonl` |
| Cursor | `cursor` | agent transcripts + `state.vscdb` |
| Cline | `cline` | VS Code `globalStorage/…/tasks/*/ui_messages.json` |
| Roo Code | `roo` | same Cline-family shape |
| Kilo Code | `kilo` | same Cline-family shape |
| Goose | `goose` | `~/.goose/sessions/*.jsonl` |
| Aider | `aider` | `~/.aider/sessions/*.jsonl` |
| Gemini CLI | `gemini_cli` | `~/.gemini/tmp/`, `~/.config/gemini/` |
| OpenCode | `opencode` | `~/.local/share/opencode/sessions/` |
| Hermes | `hermes` | `~/.hermes/sessions/*.json` |

Adding an adapter is one file + one fixture — see `cairn adapter new` ([adapters.md](docs/adapters.md)) *(scaffold lands in L6)*.

---

## How it's honest

- **Estimated tokens** are always marked with ± error chips in the UI — never presented as ground truth.
- **Verdicts** use anytime-valid confidence sequences and clustered effective sample sizes (not peeking fixed-z CIs).
- Per-adapter estimation error is published in [ACCURACY.md](ACCURACY.md) and refreshed by CI.

---

## CLI quick reference

| Command | What it does |
|---------|--------------|
| `cairn` | Golden path: sync → open dashboard |
| `cairn sync` | Ingest agent logs into `.cairn/cairn.db` |
| `cairn show ID` | Text waterfall for a trace |
| `cairn insights` | List detector insights |
| `cairn optimize` | Generate instruction proposals |
| `cairn experiments ls` | List improvement experiments |
| `cairn check` | CI quality gate (non-zero on failure) |
| `cairn export` | Export scrubbed trace bundle |
| `cairn mcp install` | Write MCP config for your agent |
| `cairn doctor` | Verify install, PATH, port, assets |
| `cairn setup-prompt` | Print agent bootstrap block |

Full reference: [docs/cli.md](docs/cli.md) (auto-generated from the action registry).

---

## Architecture

```
adapters / OTLP ──► spans ledger (SQLite) ──► incremental views
        │                      │                      │
        │                      ├── detectors / experiments
        │                      ▼
        └────────────► FastAPI ⇄ React UI (SSE) + MCP server
```

---

## Why Cairn

| Category | Examples | What Cairn adds |
|----------|----------|-----------------|
| Spend dashboards | ccusage, Tokscale | Causal traces + waste taxonomy, not just totals |
| Proxy profilers | ContextLens | Local-first, multi-agent, no proxy required |
| Eval platforms | bespoke harnesses | Measured self-improvement on your real repo |
| Observability | generic APM | Agent-native spans, fingerprint drift, optimize loop |

Nobody else combines local-first causal traces with measured instruction self-improvement.

---

## Privacy

Local-first. Loopback-only default (`127.0.0.1`). No telemetry, no accounts, no cloud sync. Export bundles are scrubbed of common secret patterns.

---

## Documentation

- [Getting started](docs/getting-started.md)
- [Concepts](docs/concepts.md)
- [UI tour](docs/ui-tour.md)
- [CLI reference](docs/cli.md)
- [API overview](docs/api.md)
- [Adapters](docs/adapters.md)
- [Optimize loop](docs/optimize.md)
- [CI gates](docs/ci.md)
- [Configuration](docs/configuration.md)
- [Legacy v3](docs/legacy-v3.md)
- [Accuracy](ACCURACY.md)

---

## Contributing · License

Adapter PRs welcome — one parser, one fixture, conformance harness green. See [CONTRIBUTING.md](CONTRIBUTING.md).

Apache-2.0 — see [LICENSE](LICENSE).
