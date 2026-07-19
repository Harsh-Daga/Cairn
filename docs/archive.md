# Portable Cairn archive (`cairn.archive.v1`)

Versioned, offline ZIP transport for workspace evidence (ADR-10). Complements scrubbed
`export_bundle` JSON and whole-DB lifecycle backup.

## Members

| File | Contents |
| --- | --- |
| `manifest.json` | Schema/producer versions, checksums, member sizes |
| `privacy.json` | Mode, retention, field classes, OTLP-loss list |
| `workspace.json` | Workspace metadata + storage/lifecycle snapshot |
| `traces.json` … `session_corrections.json` | Domain row arrays |
| `policy.json` | Advisory policy snapshot (not auto-applied on import) |

## Modes

| Mode | Behavior |
| --- | --- |
| `full` | Lossless within the selected trace limit |
| `scrubbed` | Default — redacts paths/secrets/raw text |
| `metadata_only` | Nulls `text_inline` and large JSON bodies |

## CLI / actions

```bash
cairn archive export --mode scrubbed --dry-run
cairn archive export --mode full --output /tmp/ws.zip
cairn archive inspect /tmp/ws.zip
cairn archive import /tmp/ws.zip --dry-run
cairn archive import /tmp/ws.zip --apply --conflict replace
```

Actions: `archive_export`, `archive_import`, `archive_inspect` (parity with CLI/API).

Import defaults to **dry-run**. Conflict policy: `fail` | `skip` | `replace`. Source agent logs
are never modified.

## Safety

ZIP is not a trust boundary. Readers enforce allowlisted flat members, size/ratio caps, no
symlinks, no path traversal, no duplicates. See `server/archive/safe_zip.py`.

## OTLP loss

OTLP remains supported for interoperable telemetry, but these Cairn-specific fields do **not**
round-trip through OTLP alone (also listed in `privacy.json` / inspect output):

- verification receipts / claims
- session corrections / relabels
- outcomes / quality / human labels
- diagnostics / failure localization
- data-quality / cost_source honesty fields
- span_links handoff semantics
- policy / regressions / privacy manifests
- storage retention / scrub state

See also [otlp.md](otlp.md).
