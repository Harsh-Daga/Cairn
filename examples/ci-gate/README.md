# CI quality gate

Fail a pull request when Cairn quality/cost gates regress.

```bash
cairn sync
cairn check --min-quality 0.65 --max-waste-pct 40
```

## GitHub Actions snippet

Copy [github-actions.yml](github-actions.yml) into a job step after checkout. Prefer
`uv tool install cairn-workspace` (or pin `==<version>`) so CI does not depend on the
developer machine.

Notes:

- Exit code is non-zero when gates fail.
- Sync needs adapter logs available to the runner (or use `cairn demo --reset` only for
  smoke-testing the gate wiring — not as a substitute for real workspace evidence).
- Full options: [docs/ci.md](../../docs/ci.md).
