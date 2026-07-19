# CLI domain boundaries

The supported console entry point remains `server.cli:app`. `server.cli` owns the root Typer
application, shared local runtime/action helpers, the no-command journey, generated action
subcommands, and the executable `main()` wrapper.

Command callbacks are registered from cohesive modules:

| Module | Commands |
|---|---|
| `server.cli_commands.operations` | stats, top, why, receipt, handoff, review, verify next, resource, privacy, guard, recap, UI lifecycle, upgrade, sync, doctor, check, trace display/listing, insights |
| `server.cli_commands.improvement` | optimize and experiments |
| `server.cli_commands.integrations` | export (bundle/static/session HTML), demo, MCP, configuration, rebuild, adapter tools |
| `server.cli_commands.regression` | regression create/ls/show/validate/export/import/delete (no command execution) |

The modules are imported only after the root app and helpers exist. This supports both the
installed console script and `python -m server.cli` without constructing duplicate Typer apps.
Callbacks resolve shared helpers through `server.cli`, so tests and downstream integrations that
patch `_run_action` keep the same behavior.

`scripts/gen_cli_docs.py` generates the public command index from the registered app. Compatibility
tests additionally pin the complete command hierarchy, action coverage, important option aliases,
module ownership, console entry point, and render-helper imports. A command move must not change
names, option spelling, defaults, help, exit codes, action parameters, or output unless that is a
separately specified product change.
