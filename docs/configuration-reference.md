# Generated configuration reference

Generated from `server.configuration`; edit the schema, not this table.

| Key | Type | Default | Secret |
|---|---|---|---|
| `server.host` | `str` | `'127.0.0.1'` | no |
| `server.port` | `int` | `8787` | no |
| `server.token` | `str?` | `<redacted>` | yes |
| `server.static_dir` | `pathlib.Path` | `<package>/server/static` | no |
| `server.workspace_root` | `pathlib.Path?` | `None` | no |
| `server.outcome_revert_window_hours` | `int` | `24` | no |
| `limits.five_hour_tokens` | `int?` | `None` | no |
| `budgets.daily_usd` | `float?` | `None` | no |
| `budgets.weekly_usd` | `float?` | `None` | no |
| `budgets.monthly_usd` | `float?` | `None` | no |
| `budgets.min_quality` | `float?` | `None` | no |
| `optimize.auto` | `bool` | `False` | no |
| `optimize.backend` | `str?` | `None` | no |
| `optimize.holdout` | `int` | `8` | no |
| `diagnose.changepoint_multiplier` | `float` | `2.0` | no |
| `diagnose.cascade_k` | `int` | `3` | no |
| `diagnose.cascade_waste_threshold` | `int` | `100` | no |
| `diagnose.cascade_max_events` | `int` | `2000` | no |
| `diagnose.cascade_lookahead` | `int` | `200` | no |
| `diagnose.context_rot_warning_pct` | `float` | `70.0` | no |
| `diagnose.context_rot_waste_pct` | `float` | `85.0` | no |
| `mcp.auto_install` | `bool` | `False` | no |
| `mcp.client` | `Literal['claude-code', 'cursor', 'codex', 'other']` | `'cursor'` | no |
| `policy.path_risks` | `list[server.configuration.PolicyPathRisk]` | `[]` | no |
| `policy.commands` | `list[server.configuration.PolicyCommandRule]` | `[]` | no |
| `policy.required_checks` | `list[server.configuration.PolicyRequiredCheck]` | `[]` | no |
| `policy.network_deny` | `list[str]` | `[]` | no |
| `policy.dependency_deny` | `list[str]` | `[]` | no |
| `policy.max_changed_files` | `int?` | `None` | no |
| `policy.exceptions` | `list[server.configuration.PolicyException]` | `[]` | no |
| `collection.mode` | `Literal['manual', 'efficient', 'live']` | `'efficient'` | no |
| `resources.soft_budget_bytes` | `int?` | `None` | no |
| `resources.max_file_bytes` | `int` | `33554432` | no |
| `resources.max_parse_ms` | `int` | `30000` | no |
| `resources.max_consecutive_failures` | `int` | `5` | no |
| `jobs.max_workers` | `int` | `2` | no |
| `jobs.max_queued` | `int` | `8` | no |
| `jobs.result_ttl_sec` | `int` | `3600` | no |
| `jobs.default_timeout_sec` | `int?` | `900` | no |
| `storage.mode` | `Literal['metrics', 'balanced', 'forensic', 'reference']` | `'balanced'` | no |
| `storage.text_inline_max` | `int?` | `None` | no |
| `storage.scrub_at_ingest` | `bool` | `False` | no |
| `storage.balanced_retain_days` | `int` | `14` | no |
| `lifecycle.destructive_enabled` | `bool` | `False` | no |
| `lifecycle.default_retain_days` | `int` | `90` | no |
| `tests.<project>` | `str` | — | no |
| `pricing.overrides.<model>.<field>` | typed price row | — | key-dependent |
