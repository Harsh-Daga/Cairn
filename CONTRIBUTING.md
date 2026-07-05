# Contributing

Thanks for helping improve Cairn. The project is a local-first Python tool with a bundled vanilla-JS dashboard — keep changes small, tested, and stdlib-first.

## Dev setup

```bash
git clone https://github.com/Harsh-Daga/Cairn.git && cd Cairn
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python3 -m pytest tests/ -q
```

Requires Python 3.11+. Runtime dependencies are only `httpx` and `numpy` — do not add pydantic, fastapi, pyyaml, or jinja2.

## Layout

```
The v3 Python package was archived at tag **`v3-final`**. v4 lives entirely under `server/` and `ui/`.
  cli/main.py          # all CLI commands (single file)
  ingest/              # parsers, writer, watch (incl. vscdb tail)
  ledger/              # sqlite schema + resolve
  metrics/             # compute, waste, fingerprint
  profile/             # context decomposition + detectors
  outcomes/            # git/tests quality scoring
  optimize/            # evidence → proposals → measured impact
  mcp/                 # stdio MCP server + tools
  live/server.py       # dashboard + /api/* + SSE
  render/              # dash/session payloads, scrub
  assets/              # index.html, dashboard.js, session.js, CSS
```

## LOC budget

The v3 rebuild target was ~8–10k Python LOC with only necessary code. Before adding a module, extend an existing one. Avoid duplicate helpers and narrating comments.

## Tests

```bash
python3 -m pytest tests/ -q
python3 -m pytest tests/test_ingest_cursor.py -v   # single file
```

Add tests for real behavior, not trivial assertions. Keep `tests/test_docs.py` green when changing docs.

## Design system

Dashboard uses **Surveyor's Field Notebook** (Part 18): mineral palette, Fraunces + Space Grotesk + JetBrains Mono, no pure `#000`/`#fff`, DOMPurify on all dynamic HTML. See `tests/test_assets_design.py` for guards.

## Pull requests

- One logical change per PR when possible
- `python3 -m pytest tests/ -q` green
- Update docs if CLI or behavior changes
- No commits to unrelated formatting
