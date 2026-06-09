# End-to-end manual testing guide

Hands-on checklist to exercise **every major Cairn feature** using the demo corpus in
[`examples/e2e-demo/`](../../examples/e2e-demo/).

**Time:** ~45–60 minutes (live provider build + real Claude Code session).

**Providers:** setup defaults to **local Ollama** (`ollama/llama3.2`). Use
`--provider cloud` for **Ollama Cloud** + `kimi-k2.6:cloud` (same as `cairn init`).

---

## 0. Prerequisites

```bash
# Install Cairn (pick one)
pip install cairn-workspace
# pipx install cairn-workspace
# uv tool install cairn-workspace
# curl -fsSL https://raw.githubusercontent.com/Harsh-Daga/Cairn/main/install.sh | bash

cairn --version

# Clone Cairn (for demo files + test fixtures)
git clone https://github.com/Harsh-Daga/Cairn.git ~/Cairn
```

### Create the test repo

```bash
chmod +x ~/Cairn/examples/e2e-demo/setup.sh

# Default — local Ollama + llama3.2
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test

# Or Ollama Cloud + kimi-k2.6 (recommended if you have OLLAMA_CLOUD_API_KEY)
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test --provider cloud

# Or pick any model string
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test --model ollama-cloud/kimi-k2.6:cloud
~/Cairn/examples/e2e-demo/setup.sh ~/cairn-e2e-test --provider local --model llama3.2

cd ~/cairn-e2e-test
grep '^model' cairn.toml    # confirm provider/model
```

This gives you a **git repo** with three markdown notes, a spec, prompts, and `cairn.toml`
with the model you chose (`ollama/llama3.2` by default).

---

## Part A — Provider pipeline

### A1. Offline smoke (no LLM, recorded fixtures)

Verifies CLI, graph, cache, and render without spending tokens.

```bash
cd ~/cairn-e2e-test

cairn validate
cairn status
cairn plan
cairn build --yes --provider-mode recorded
cairn runs
cairn report --json | head -40
cairn render -o outputs/bundle-recorded --zip
open outputs/bundle-recorded/index.html    # macOS
# xdg-open outputs/bundle-recorded/index.html   # Linux
```

**Expect:** `outputs/report.md`, `outputs/summaries/*.md`, HTML bundle opens offline.

### A2. Live provider build

Pick **one** path matching your `cairn.toml` model (from setup).

#### A2a. Ollama Cloud + kimi-k2.6 (if you used `--provider cloud`)

`kimi-k2.6:cloud` is a **reasoning** model — use `max_tokens = 4096` or higher in
`cairn.toml` (the cloud setup script does this automatically). After a recorded build,
force live with `--refresh`.

```bash
export OLLAMA_CLOUD_API_KEY='your-key'

cd ~/cairn-e2e-test
grep '^model' cairn.toml    # expect: ollama-cloud/kimi-k2.6:cloud
grep max_tokens cairn.toml  # expect: 4096 for cloud

cairn doctor
cairn build --yes --provider-mode live --refresh summaries
cairn runs
cairn report --json
cairn render -o outputs/bundle-live --zip
open outputs/bundle-live/index.html
```

#### A2b. Local Ollama + llama3.2 (default setup)

```bash
# Terminal 1 — start Ollama if not already running
ollama serve

# Terminal 2
ollama pull llama3.2
export OLLAMA_HOST=http://127.0.0.1:11434

cd ~/cairn-e2e-test
grep '^model' cairn.toml    # expect: ollama/llama3.2

cairn doctor
cairn build --yes --provider-mode live
cairn runs
cairn report --json
cairn render -o outputs/bundle-live --zip
open outputs/bundle-live/index.html
```

**Expect:** New provider run in `cairn runs`; summaries differ from recorded run if the model
responds.

To switch provider later, edit `model` in `cairn.toml` or re-run setup into a new directory.

### A3. Project context + prompts + workflows

```bash
cd ~/cairn-e2e-test

cairn context scan
cairn context list
cairn context show <asset-id-from-list>

cairn prompt sync
cairn prompt list
cairn prompt show summarize

cairn workflow list
cairn workflow validate
cairn workflow run --dry-run
cairn workflow run --yes --provider-mode recorded
```

### A4. Dependency graph (provider pipeline)

```bash
cd ~/cairn-e2e-test

# Session id is ignored for --kind dependency; project graph from cairn.toml
cairn graph _ --kind dependency --format json | head -30
```

Capture session graphs (execution / artifact) are in **B1** after ingest.

### A5. Snapshots

```bash
cd ~/cairn-e2e-test

cairn snapshot create --label before-edit --json
echo "# Delta note" >> inputs/notes/alpha.md
cairn snapshot create --label after-edit --json
cairn snapshot list
cairn snapshot diff <before-id> <after-id>
```

### A6. Collaboration export (with ACL)

```bash
cd ~/cairn-e2e-test

cairn collab export /tmp/cairn-sync-out --generate-token
# Save the printed access token

mkdir -p ~/cairn-e2e-import
cd ~/cairn-e2e-import
git init
cairn collab import /tmp/cairn-sync-out --token '<paste-token>'
cairn collab status
```

### A7. Security

```bash
cd ~/cairn-e2e-test

cairn security audit
export CAIRN_ENCRYPTION_KEY='demo-passphrase'
cairn security encrypt outputs/bundle-live.zip outputs/bundle-live.zip.enc
cairn security decrypt outputs/bundle-live.zip.enc /tmp/bundle-restored.zip
ls -la /tmp/bundle-restored.zip
```

### A8. HTTP API

```bash
cd ~/cairn-e2e-test

export CAIRN_API_TOKEN=demo-token
cairn api serve --port 8790 &
sleep 1

curl -s -H "Authorization: Bearer demo-token" \
  http://127.0.0.1:8790/v1/openapi.json | head

curl -s -H "Authorization: Bearer demo-token" \
  http://127.0.0.1:8790/v1/projects/cairn-e2e-test/sessions

# Stop background server
kill %1
```

### A9. Python SDK

```bash
cd ~/cairn-e2e-test
python3 << 'PY'
import cairn
from cairn.workflow import run as workflow_run
from cairn.render import html, report_json

project = cairn.Project.open(".")
run = workflow_run(project=project, yes=True, provider_mode="recorded")
print(report_json(run)["kind"])
html(run, output=project.root / "outputs" / "sdk-bundle")
print("Wrote outputs/sdk-bundle/index.html")
PY
```

---

## Part B — Agent capture (Claude Code)

Capture uses the **same git repo**. Cairn finds Claude transcripts under
`~/.claude/projects/<slug>/` where `<slug>` is your repo path with `/` → `-`.

### B1. Simulated ingest (no Claude session required)

Use the redacted test fixture to verify capture → render without running an agent.

```bash
cd ~/cairn-e2e-test

# Slug for this repo path (example; run the python line to get yours)
python3 -c "from pathlib import Path; print(Path('.').resolve().as_posix().replace('/','-'))"

# Example output: -Users-you-cairn-e2e-test
CLAUDE_SLUG="$(python3 -c "from pathlib import Path; print(Path('.').resolve().as_posix().replace('/','-'))")"
mkdir -p "$HOME/.claude/projects/$CLAUDE_SLUG"
cp ~/Cairn/tests/fixtures/ingest/claude_code_mini.jsonl \
   "$HOME/.claude/projects/$CLAUDE_SLUG/sess-e2e-demo.jsonl"

cairn ingest --source claude-code --json
cairn sessions list
cairn show sess-redacted-001
cairn graph sess-redacted-001 --kind execution
cairn graph sess-redacted-001 --kind artifact
cairn report --session sess-redacted-001 --json | head -40
cairn artifact list sess-redacted-001
cairn render --session sess-redacted-001 -o outputs/capture-bundle
open outputs/capture-bundle/index.html
```

### B2. Real Claude Code session

```bash
cd ~/cairn-e2e-test

# Install capture hooks (writes .claude/settings.local.json)
cairn live install --source all
cairn watch status
cairn live status

# In Claude Code (same directory ~/cairn-e2e-test), run a short task, e.g.:
#   "Read inputs/notes/alpha.md and suggest one improvement."

# After the session ends:
cairn ingest --source claude-code
cairn sessions list
SESSION_ID="<paste-from-list>"

cairn show "$SESSION_ID"
cairn render --session "$SESSION_ID" -o outputs/capture-live
cairn live serve --session "$SESSION_ID" --port 8787
# Open http://127.0.0.1:8787/session/<SESSION_ID>
```

### B3. Incremental ingest

```bash
cd ~/cairn-e2e-test
cairn ingest --source claude-code    # should skip unchanged files
cat .cairn/watch/cursors.json
```

### B4. Session diff

```bash
cd ~/cairn-e2e-test
cairn diff <session-id-a> <session-id-b>
```

### B5. Uninstall hooks

```bash
cd ~/cairn-e2e-test
cairn live uninstall
cairn watch uninstall
```

---

## Part C — Other ingest sources (optional)

Run only if you use these tools.

| Source | Ingest command |
|--------|----------------|
| Codex | `cairn ingest --source codex` |
| Cursor | `cairn ingest --source cursor` |
| Hermes | `cairn ingest --source hermes` |
| All | `cairn ingest --source all` |

Then repeat: `sessions list` → `show` → `render --session`.

---

## Quick reference — command checklist

| # | Feature | Command |
|---|---------|---------|
| 1 | Install | `pip install cairn-workspace` |
| 2 | Scaffold | `setup.sh ~/cairn-e2e-test` or `--provider cloud` |
| 3 | Validate | `cairn validate` |
| 4 | Doctor | `cairn doctor` |
| 5 | Recorded build | `cairn build --yes --provider-mode recorded` |
| 6 | Live build | `cairn build --yes --provider-mode live` |
| 7 | Plan / status | `cairn plan` / `cairn status` |
| 8 | Context | `cairn context scan` |
| 9 | Prompts | `cairn prompt sync` |
| 10 | Workflows | `cairn workflow run` |
| 11 | Runs / report | `cairn runs` / `cairn report --json` |
| 12 | Render | `cairn render -o outputs/bundle --zip` |
| 13 | Graph | `cairn graph <step> --kind execution` |
| 14 | Snapshot | `cairn snapshot create` |
| 15 | Collab | `cairn collab export` / `import` |
| 16 | Security | `cairn security audit` |
| 17 | API | `cairn api serve` |
| 18 | Capture ingest | `cairn ingest --source claude-code` |
| 19 | Live UI | `cairn live serve --session <id>` |
| 20 | Hooks | `cairn live install` |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `cairn: command not found` | Add `~/.local/bin` to `PATH` |
| `doctor` fails (local) | Run `ollama serve` and `ollama pull llama3.2` |
| `doctor` fails (cloud) | Set `OLLAMA_CLOUD_API_KEY`; model `ollama-cloud/kimi-k2.6:cloud` |
| `build --live` hangs | Check credentials, `OLLAMA_HOST` (local), model in `cairn.toml` |
| `EmptyCompletionError` (cloud) | Raise `max_tokens` to 4096+; use `--refresh` after recorded |
| Live build all `CACHED` | Add `--refresh summaries` (or wipe `.cairn/cache`) |
| No Claude sessions | Confirm `git` root matches cwd; check `~/.claude/projects/` slug |
| Empty capture bundle | Run `cairn ingest` after session; try fixture in B1 |
| `zsh: parse error near ')'` | Paste one command block at a time; avoid comment lines with `(` |
| `security encrypt` crashes | Reinstall from source: `uv tool install --reinstall .` |
