# Guard — instruction-file edit observation

Guard watches local git history for instruction files (`AGENTS.md`, `CLAUDE.md`,
`.cursor/rules`) and records scrubbed edit events. Session metrics around each event are
reported as **associations** (“associated with” / “observed after”), never as causal proof that
the edit caused the shift.

## Surfaces

| Surface | Role |
|---------|------|
| UI `/guard` | Ledger, event list, scrubbed diff summary, association intervals |
| `GET /api/analytics/guard` | Same payload; static export captures it per day window |
| `cairn guard` | Text/JSON listing of events and association verdicts |
| Overview trend annotations | `kind=guard` deep-links when events exist |
| Optimize | `guard_event_id` links when an applied experiment matches an event window |

## States

- **edit / rename / revert / merge** — classified from git status and commit subject/parents
- **dirty_snapshot** — uncommitted instruction changes in the worktree
- **unavailable** — workspace is not a git repository
- **confounded / inconclusive** — association windows fail mix guards or lack sample size

## Honesty rules

- Diff summaries are scrubbed (paths, secrets, code fragments redacted).
- Raw instruction text is not exported by default.
- Association uses the same difference-in-means + anytime-valid interval machinery as Optimize
  holdout measurement, with explicit confound notes.
- Renames, merges, reverts, dirty trees, and no-git workspaces are first-class, not silent failures.
