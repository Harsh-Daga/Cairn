# Contributing

Thanks for helping improve Cairn. The application lives under `server/` (Python) and `ui/` (React/Vite).

## Dev setup

```bash
git clone https://github.com/Harsh-Daga/Cairn.git && cd Cairn
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"
python scripts/build_ui.py
uv run pytest -q
uv run ruff check .
uv run mypy --strict server
```

Requires Python 3.11+. UI: Node 22+, `cd ui && npm ci && npx tsc --noEmit`.

## Adapter PRs

1. Add parser under `server/ingest/adapters/`
2. Register in `server/ingest/registry.py`
3. Add fixture under `tests/fixtures/ingest/`
4. Run conformance: `uv run pytest tests/adapter_conformance.py`

One parser + one fixture + harness green = mergeable adapter PR.

## Style gates

- Modules ≤ 400 lines
- No SQL outside `server/store/`
- `mypy --strict`, `ruff`, `tsc` clean
- No CDN URLs (`tests/test_cdn_grep.py`)
- Mutations through action registry only (CLI/API/UI parity)
- Regenerate `docs/cli.md` when changing CLI or actions: `python scripts/gen_cli_docs.py`

## Tests

```bash
uv run pytest -q
uv run pytest tests/test_docs.py -q   # docs + CLI surface
```

## README media

README screenshots are captures of the real deterministic demo workspace, not mock artwork. After
a UI change, run `cairn demo --reset`, start `cairn ui --workspace ~/.cairn-demo --no-open`, then
run `uv run python scripts/gen_readme_assets.py`. Use `--base-url` when the dashboard is on a
non-default port.

## Pull requests

- One logical change per PR when possible
- Update docs when CLI or behavior changes
- Keep `tests/test_docs.py` green
