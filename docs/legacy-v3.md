# Legacy v3 tree (`cairn/`)

The v3 Python package was removed in **Cairn 1.0.0**. A snapshot remains on the git tag **`v3-final`** for reference.

## v3 → v4 mapping

| v3 (`cairn/`) | v4 (`server/`) |
|---------------|----------------|
| `ledger.db` | `cairn.db` at `.cairn/cairn.db` |
| `cairn/live/server.py` | `server/app.py` + `server/cli.py` |
| Monolithic CLI (`cairn/cli/main.py`) | Typer CLI with action registry |
| `runs` / `events` tables | `traces` / `spans` |
| Insights rules in `cairn/insights/` | `server/analyze/detectors/` + incremental views |

## Upgrade notes

- **No automatic migration** — v4 opens a fresh SQLite schema. Re-run `cairn sync` to ingest logs from adapters.
- **Config path unchanged** — `~/.config/cairn/config.toml` (some keys renamed; see [configuration.md](configuration.md)).
- **CLI entry point** — `cairn` maps to `server.cli:app`; v3 verbs (`init`, `validate`, `build`) are gone.

## Recovering v3 code

```bash
git fetch --tags
git checkout v3-final -- cairn/
```

Do not merge v3 paths back into main — algorithms were ported into `server/` during the v4 rewrite.
