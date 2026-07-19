# Advisory policies

Cairn can evaluate a typed `[policy]` section from user/workspace config against **recorded**
session evidence. Findings are advisory observations. They never claim that Cairn blocked,
sandboxed, or prevented an action.

## Configuration

```toml
[policy]
max_changed_files = 40

[[policy.path_risks]]
pattern = "**/auth/**"
risk = "high"

[[policy.commands]]
pattern = "rm\\s+-rf"
mode = "forbidden"   # or "advisory"
reason = "destructive cleanup"

[[policy.required_checks]]
paths = ["**/auth/**"]
checks = ["tests", "build"]

[[policy.exceptions]]
id = "build-clean"
reason = "local artifact cleanup"
commands = ["rm\\s+-rf build"]
```

Empty policy still evaluates as `review_risk=none` with an explicit limitation.

## Enforcement sources

Each finding includes `enforcement_source`:

| Value | Meaning |
|-------|---------|
| `observed_violation` | Ledger evidence matched a rule |
| `advisory_warning` | Soft warning (e.g. missing required checks) |
| `allowlisted_exception` | Match covered by a documented exception |

## Where it runs

- Verification receipt `risk_policy` (`cairn.receipt.v1`)
- `cairn check` (high/observed findings become gate failures with sources)
- Session filter `risk:high` (conservative path/command proxies)

MCP `cairn_policy_check` and `cairn review` arrive in later Phase 5 tasks.
