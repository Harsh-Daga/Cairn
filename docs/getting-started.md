# Getting Started with Cairn

Cairn unifies **agent capture** and **provider workflows** in one local workspace.
All execution paths write to `.cairn/ledger.db` and the content-addressable store.

## 1. Scaffold a project

```bash
uv run cairn init my-project
cd my-project
uv run cairn validate
uv run cairn doctor
```

`cairn.toml` defines sources, prompts, and build steps. Workflows extend this model via
`cairn workflow list` and `cairn workflow run`.

## 2. Run a provider build

```bash
uv run cairn status
uv run cairn build --yes --provider-mode recorded
uv run cairn runs
uv run cairn render -o outputs/bundle
```

Recorded mode replays fixtures for CI. Live mode calls configured providers using env-var
credentials only.

## 3. Capture agent sessions

From a git repository where agents have run:

```bash
uv run cairn ingest --source claude-code
uv run cairn sessions list
uv run cairn graph <session_id> --kind execution
uv run cairn report --session <session_id> --json
```

Incremental ingest skips unchanged transcript files using `.cairn/watch/cursors.json`.

## 4. Live workspace

```bash
uv run cairn live serve --port 8787
# open http://127.0.0.1:8787/session/<session_id>
```

The browser loads a split bundle and subscribes to SSE for live updates.

## 5. Share and reproduce

```bash
uv run cairn snapshot create --label baseline
uv run cairn collab export /path/to/sync-bundle
uv run cairn render --session <id> -o outputs/bundle --zip
uv run cairn security encrypt outputs/bundle.zip outputs/bundle.zip.enc
```

## 6. Programmatic access

```python
from cairn.workflow import run as workflow_run
from cairn.render import html, report_json
import cairn

project = cairn.Project.open(".")
run = workflow_run(project=project, yes=True)
report_json(run)
html(run)
```

Or start the HTTP API:

```bash
uv run cairn api serve
```
