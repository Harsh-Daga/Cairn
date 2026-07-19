# Local regression artifacts

Cairn can turn a recorded failure into a **portable local regression artifact** under
`.cairn/regressions/<id>/`. The format is versioned as `cairn.regression.v1`.

## What is stored

| Field | Meaning |
|-------|---------|
| Scrubbed task | Intent from receipt / first user message (paths and secrets redacted) |
| Repo start ref | Commit from outcome/trace when recorded, otherwise a limitation |
| Setup commands | Always empty on create — Cairn does not invent a setup script |
| Verification commands | **Inferred** span-name hints only; never executed |
| Expected outcome | Recorded tests/build/label/failure signature |
| Runs | Later observed outcomes recorded from ingested sessions |
| Privacy inventory | What was included vs redacted |
| Attachments | Empty by default (no working-tree copy) |

Artifacts do **not** copy the private repository, full transcripts, or run any commands.
Definition `content_hash` excludes `runs` so recording observations does not change identity.

## CLI

```bash
cairn regression create <trace_id> [--json]
cairn regression ls [--json]
cairn regression show <id> [--json]
cairn regression validate <id> [--json]
cairn regression run <id> --trace <trace_id> [--json]
cairn regression compare <id> [--run <run_id>] [--against expected|<run_id>] [--json]
cairn regression export <id> -o ./reg.zip [--json]
cairn regression import ./reg.zip [--replace] [--json]
cairn regression delete <id> --yes
```

- **run** appends one `RegressionRun` from an already-ingested session. It never re-runs the
  agent or executes setup/verification command hints (`executed_commands` is always false).
- **compare** diffs expected outcome (or another run) against a recorded run. Verdicts are
  `match`, `mismatch`, or `insufficient` when a compared field is missing on one side.

Validate checks schema and honesty constraints only. Export/import use zip archives with
path-traversal and symlink rejection; import skips attachments by default and re-scrubs text
against the destination workspace.

## Actions

Registered actions (same handlers as CLI): `regression_create`, `regression_run`,
`regression_compare`, `regression_delete`, `regression_export`, `regression_import`.

## Honesty limits

- Cairn never executes setup or verification command hints.
- Inferred verification commands are documentation hints, not a test runner.
- Missing commit/fixture is reported as a limitation, not invented.
- Compare is a descriptive outcome rollup diff, not a CI test runner.

See also: [verification receipts](data-model.md), [CLI reference](cli.md).
