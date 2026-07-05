# CI gates

Use Cairn in CI to block merges when agent quality regresses.

## Basic gate

```bash
cairn sync
cairn check
```

`cairn check` runs the registered `check` action. Exit code is non-zero when gates fail.

## Threshold flags

```bash
cairn check --min-quality 0.65
cairn check --max-waste-pct 40
```

## GitHub Actions snippet

```yaml
- uses: astral-sh/setup-uv@v5
- run: uv tool install cairn-workspace
- run: |
    export PATH="$(uv tool dir --bin):$PATH"
    cd "${{ github.workspace }}"
    cairn sync
    cairn check --min-quality 0.6
```

## Tail cost gate (L4)

```bash
cairn check --max-tail-cost 25
```

Fails when projected worst-session cost over the next 1000 sessions exceeds the threshold (uses tail return-level estimate).

## Doctor in CI

After install:

```bash
cairn doctor --json
```

## Related

- [Optimize loop](optimize.md) — experiment verdicts
- [Configuration](configuration.md) — `[budgets]` thresholds
