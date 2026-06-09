# Cairn

Local-first inference workspace for AI agents and direct LLM/provider workflows.
Capture agent sessions, run versioned workflows, and render self-contained HTML reports
from a single ledger and content-addressable store.

See [CHARTER.md](CHARTER.md) for the full specification (v3.0).

## Install

```bash
uv sync --group dev
uv pip install -e .
uv run cairn --version
```

## Command groups

```bash
uv run cairn help
```

| Group | Commands |
|-------|----------|
| Project | `init`, `validate`, `doctor`, `status`, `plan` |
| Workflows | `context`, `prompt`, `workflow`, `build` |
| Capture | `ingest`, `watch`, `hook`, `sessions`, `show`, `live` |
| Observability | `runs`, `render`, `report`, `graph`, `artifact`, `diff` |
| Sharing | `snapshot`, `collab` |
| API | `api` |
| Security | `security` |

## Quickstart — provider workflow

```bash
uv run cairn init my-project && cd my-project
uv run cairn validate && uv run cairn doctor
uv run cairn workflow list
uv run cairn build --yes --provider-mode recorded   # offline replay (CI default)
uv run cairn render -o outputs/bundle --zip
uv run cairn report --json
```

Set provider credentials via environment variables (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`,
`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, etc.). Use `--provider-mode live` for real APIs.

## Quickstart — agent capture

```bash
cd your-repo
uv run cairn ingest --source claude-code
uv run cairn sessions list
uv run cairn show <session_id>
uv run cairn render --session <session_id> -o outputs/capture-bundle
uv run cairn live serve --session <session_id>   # http://127.0.0.1:8787
```

Supported ingest sources: `claude-code`, `codex`, `cursor`, `hermes`, `aider`, `openhands`,
`goose`, and `all`.

## Python SDK

```python
import cairn
from cairn.workflow import run as workflow_run
from cairn.render import html

project = cairn.Project.open(".")
run = workflow_run(project=project, yes=True, provider_mode="recorded")
html(run, output=project.root / "outputs" / "bundle")
```

## HTTP API

```bash
export CAIRN_API_TOKEN=local-dev-token   # optional bearer auth
uv run cairn api serve --port 8790
curl -H "Authorization: Bearer local-dev-token" http://127.0.0.1:8790/v1/openapi.json
```

See [docs/api.md](docs/api.md) for route details.

## Documentation

- [Getting started](docs/getting-started.md)
- [HTTP API](docs/api.md)
- [Security](docs/security.md)
- [Architecture audit](docs/architecture-audit.md)
- [Build progress](PROGRESS.md)

## Development

```bash
uv run pytest
uv run ruff check cairn tests
uv run mypy cairn
```

200+ tests. Charter v3.0 phases 0–22 complete — release 1.0.
