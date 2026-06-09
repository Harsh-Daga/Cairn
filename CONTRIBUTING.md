# Contributing to Cairn

Thank you for your interest in Cairn. This project is Apache-2.0 licensed.

## Development setup

```bash
git clone https://github.com/Harsh-Daga/Cairn.git
cd Cairn
uv sync --group dev
uv pip install -e .
```

## Running tests

```bash
uv run pytest -q
uv run ruff check cairn tests
uv run mypy cairn
```

CI expectations: all tests pass, ruff clean, mypy strict clean.

## Project layout

```
cairn/           # Python package
  cli/           # Command-line interface
  ingest/        # Agent transcript parsers
  render/        # HTML bundle generation
  workflow/      # Workflow engine
  api/           # HTTP server
  sdk/           # Public Python API
tests/           # pytest suite
docs/            # User and contributor documentation
```

## Design references

- [Technical charter](docs/spec/charter.md) — full product and implementation specification
- [Documentation index](docs/README.md) — user guides and CLI reference

Read the charter before large changes. New parsers, providers, and report fields should follow
existing patterns and extend the registry model rather than branching core logic.

## Pull requests

1. Fork and create a feature branch
2. Add or update tests for behavior changes
3. Run `pytest`, `ruff`, and `mypy` locally
4. Write a clear PR description: what changed and why

Keep diffs focused. Prefer extending registries (agents, providers, render) over one-off
special cases.

## Code style

- Python 3.11+, type hints required (mypy strict)
- Ruff for lint and import order
- Imports at top of file
- Comments only for non-obvious logic

## Reporting issues

Include:

- Cairn version (`cairn --version`)
- OS and Python version
- Minimal steps to reproduce
- Redacted logs or bundle excerpts when relevant

Do not paste API keys or unscrubbed session transcripts in public issues.
