# Deterministic end-to-end demo

Use this example to get **time-to-first-evidence** without a model provider.

## Fastest path (CI / Pages)

```bash
cairn demo --reset
cairn ui --workspace "$HOME/.cairn-demo"
cairn check --workspace "$HOME/.cairn-demo"
cairn receipt <trace_id> --workspace "$HOME/.cairn-demo"
```

`cairn demo --reset` seeds a fixed local workspace under `~/.cairn-demo` (120 traces).
Open Overview → Sessions → a session Receipt tab, or use `cairn receipt`.

Static snapshot for file:// / Pages:

```bash
uv run python scripts/build_ui.py build
uv run python scripts/prepare_e2e_static.py /tmp/cairn-static
```

## Workspace skeleton (optional)

Copy a sample `.cairn/config.toml` into a disposable git repo:

```bash
./examples/e2e-demo/setup.sh ~/cairn-e2e-demo
```

Then either seed the shared demo workspace above, or run `cairn sync` in the new repo after
you have local agent logs.

## Honesty

- Demo data is synthetic and deterministic — not your production agent history.
- `cairn check` gates use configured budgets/quality thresholds; tune via config.
- Receipts are evidence, not cryptographic attestations.

See also: [ci-gate](../ci-gate/), [export-archive](../export-archive/), [pages](../../docs/pages.md).
