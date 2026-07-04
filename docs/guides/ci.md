# CI gates

`cairn check` exits 0 when all gates pass, 1 when any **error**-severity issue is found.

## Gates

```bash
cairn check --budget-usd 50.00
cairn check --budget-tokens 1000000
cairn check --max-waste-ratio 0.30 --days 7
cairn check --min-quality 70          # 7d mean quality_score from outcomes
cairn check --json
```

The dashboard **Settings → Run check** button calls `POST /api/action/check` with the same logic.

### Quality gate

Requires outcomes in the ledger (git/test signals captured during sync). Compares the 7-day mean `quality_score` against `--min-quality`.

## GitHub Actions example

```yaml
name: Cairn gates
on: [push]

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install cairn-workspace
      - run: cairn sync && cairn check --min-quality 70 --format github
```

## Severity levels

| Level | Effect |
|-------|--------|
| `info` | Gate passed |
| `warning` | Informational (e.g. no ledger yet) |
| `error` | Gate failed → exit 1 |

## 5-hour plan window

If `limits.five_hour_tokens` is set in `~/.config/cairn/config.toml`, `cairn check` includes a Codex-style rolling window gate automatically.
