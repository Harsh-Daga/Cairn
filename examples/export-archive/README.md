# Scrubbed export and portable archive

## Static UI snapshot

```bash
uv run python scripts/build_ui.py build
cairn demo --reset
cairn export --static /tmp/cairn-static --workspace "$HOME/.cairn-demo"
```

Open `/tmp/cairn-static/index.html` (or serve under `/Cairn/` — see [docs/pages.md](../../docs/pages.md)).
Mutations and live SSE are disabled in static mode.

## Portable archive (`cairn.archive.v1`)

```bash
cairn archive export --mode scrubbed --dry-run
cairn archive export --mode scrubbed --output /tmp/workspace.cairn.zip
cairn archive inspect /tmp/workspace.cairn.zip
```

Import defaults to dry-run; review conflict policy before applying. Details:
[docs/archive.md](../../docs/archive.md).

## Session export bundle

```bash
cairn export <trace_id>
```

Produces a scrubbed local bundle under `.cairn/exports/`. Pattern scrubbing is best-effort —
review before sharing.
