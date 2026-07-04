# Optimize guide

Cairn closes the loop: evidence → instruction-file changes → **measured** impact on a holdout window.

## Preview

```bash
cairn optimize
```

Lists proposals with evidence traces. Nothing is written until you apply.

## Apply

```bash
cairn optimize --apply
```

Writes managed blocks inside target files:

```html
<!-- cairn:managed start ... -->
<!-- cairn:managed end -->
```

Targets: `CLAUDE.md`, `AGENTS.md`, `.cursor/rules`, project instruction files.

## Dashboard

Open **Optimize** in the sidebar. Click **Find improvements**, review proposals, **Apply** or **Revert** per rule.

## Measurement

After apply, Cairn measures waste ↓, fingerprint stability, and quality ↑ on a **holdout** of sessions the proposer never saw. Rules are selected via Thompson sampling; hard-pruned only after repeated holdout failure.

## Optional LLM reflector

Set `optimize.reflector = "httpx"` in config and provide an API key. Falls back to templated rewrites from evidence when unavailable.

## Revert

```bash
cairn optimize --revert OPT_ID
```

Or use **Revert** on the Optimize page.

## Config

```toml
[optimize]
auto = false
holdout = 5
prune_threshold = 0.2
reflector = "template"
```
