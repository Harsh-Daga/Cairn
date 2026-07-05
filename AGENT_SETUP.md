# Agent setup prompt for Cairn

You are setting up **Cairn** for the user's current repository. Cairn is local-first agent observability — no cloud, no accounts.

## Rules

- Never use `sudo` or modify system Python.
- Write only inside the user's home tool dirs, this repo, and this agent's own MCP config.
- The Cairn server binds to `127.0.0.1` only.
- If any **VERIFY** step fails, stop and print the **DIAGNOSE** section output instead of improvising.
- This prompt is idempotent — safe to run twice.

## Step 0 — detect environment

Run:

```bash
uname -a 2>/dev/null || echo "OS=$env:OS"
echo "SHELL=$SHELL"
command -v uv || true
command -v pipx || true
command -v pip3 || command -v pip || true
python3 --version 2>/dev/null || python --version
```

Pick HTTP port **8787** unless busy; if busy, try 8788, 8789, … and remember the choice.

Port check (bash):

```bash
python3 - <<'PY'
import socket
for port in range(8787, 8792):
    s = socket.socket()
    s.settimeout(0.3)
    free = s.connect_ex(("127.0.0.1", port)) != 0
    s.close()
    print(f"{port}:{'free' if free else 'busy'}")
PY
```

**VERIFY:** You recorded OS, shell, available installers, Python version, and chosen port.

## Step 1 — install Cairn

Preference order:

1. `uv tool install cairn-workspace` (or `uv tool install cairn-workspace==4.0.0` to pin)
2. `pipx install cairn-workspace`
3. `pip install --user cairn-workspace`

If none exist, bootstrap uv (no sudo):

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install cairn-workspace
```

Ensure `cairn` is on PATH:

```bash
export PATH="$(uv tool dir --bin 2>/dev/null):$PATH"
cairn --version
```

**VERIFY:** `cairn --version` prints `4.` (e.g. `4.0.0`).

## Step 2 — initialize in this repo

From the repository root:

```bash
cairn sync
cairn ui --no-open --port <PORT> &
sleep 2
curl -s http://127.0.0.1:<PORT>/api/health
cairn action workspace_scan
```

**VERIFY:** health JSON contains `"status":"ok"` (or `"ok"` field). `workspace_scan` lists ≥0 paths; if 0, print supported agents (Claude Code, Codex, Cursor, Cline, Roo, Kilo, Goose, Aider, Gemini CLI, OpenCode, Hermes, OpenClaw) and continue.

## Step 3 — connect Cairn to you (the agent)

Detect which agent is executing (Claude Code / Cursor / Codex / other). Run:

```bash
cairn mcp install --client <self>
```

For **other**, run `cairn mcp install --client other --print` and tell the user where to paste the JSON block.

**VERIFY:** The MCP config file now contains a `cairn` server entry (or you printed exact paste instructions for unsupported clients).

## Step 4 — seed instructions (propose only)

```bash
cairn action optimize_propose --params-json '{"apply": false, "llm": false}'
```

Show the proposed diff for the repo's `AGENTS.md` or `CLAUDE.md` managed block. **Never auto-apply** — ask the user first.

**VERIFY:** You displayed the proposal and asked before writing.

## Step 5 — report

Print this summary:

```
Cairn setup complete
- install: <method>
- version: <cairn --version>
- dashboard: http://127.0.0.1:<PORT>
- adapters: <n streams from workspace_scan>
- MCP: <installed|manual paste at path>
Commands to remember: cairn | cairn stop | cairn insights
```

## DIAGNOSE

| Failure | Fix |
|---------|-----|
| `cairn: command not found` after uv install | `export PATH="$(uv tool dir --bin):$PATH"` |
| Port busy | `cairn ui --port 8788 --no-open` |
| Python < 3.11 | Install Python 3.11+; recreate venv |
| No logs / 0 adapters yet | Run an agent session, then `cairn sync` again |
| Browser won't open (WSL) | Use `--no-open` and open URL manually |
| PyPI blocked | Use `UV_INDEX` mirror or offline wheel via `pip install ./dist/*.whl` |
