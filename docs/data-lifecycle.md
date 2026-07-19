# Data lifecycle

Cairn helps manage **copied** workspace data under `.cairn/` without touching agent source logs.

## Defaults (warn-only)

| Setting | Default | Meaning |
| --- | --- | --- |
| `[lifecycle].destructive_enabled` | `false` | Delete/restore stay blocked until explicitly enabled |
| `[lifecycle].default_retain_days` | `90` | Age window for plan/cleanup when `retain_days` is omitted |

`retain_days=0` means no age filter (all matching Cairn rows in the workspace).

## Actions (CLI/UI/API parity)

| Action | Purpose |
| --- | --- |
| `lifecycle_plan` | Dry-run counts (never mutates) |
| `lifecycle_cleanup` | `strip_text` (null `text_inline`, keep hashes/metrics) or `delete_traces` |
| `db_backup` | SQLite backup into `.cairn/backups/manual/` |
| `db_backup_list` | List newest backups under `.cairn/backups/manual/` (bounded) |
| `db_restore` | Replace `cairn.db` from a path under `.cairn/` (`dry_run` preview, then confirm + destructive flag) |
| `db_integrity` | `PRAGMA quick_check` + foreign-key check |
| `db_compact` | WAL checkpoint + `VACUUM` (confirmed) |

Examples:

```bash
cairn action lifecycle_plan --params '{"mode":"strip_text"}'
cairn action lifecycle_cleanup --params '{"mode":"strip_text","confirm":true}'
cairn action db_backup --params '{"label":"pre-compact"}'
cairn action db_backup_list
cairn action db_restore --params '{"backup":".cairn/backups/manual/….db","dry_run":true}'
cairn action db_integrity
cairn privacy --json   # includes lifecycle + integrity summary
```

Settings → Resource & Privacy exposes the same backup list → dry-run → typed `RESTORE` flow.

## Guarantees and limits

- Cleanup **never** deletes Cursor/Claude/etc. source logs — only Cairn copies/indexes.
- Destructive delete/restore require `[lifecycle].destructive_enabled = true` **and** `confirm=true`.
- `dry_run=true` on restore never mutates files; it reports integrity and whether a pre-restore
  backup would be written.
- Restore refuses paths outside the workspace `.cairn/` tree (symlink/traversal protected).
- Strip/delete are **resumable** via `limit`; re-run until dry-run counts reach zero for the window.
- Compaction rewrites the DB file — take a backup first on large workspaces.

See also: [storage modes](storage-modes.md), [resource shield](resource-shield.md).
