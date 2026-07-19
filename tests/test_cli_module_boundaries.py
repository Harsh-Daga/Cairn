from __future__ import annotations

from typer.main import get_command

from server import cli

EXPECTED_TOP_LEVEL = {
    "action",
    "adapter",
    "archive",
    "check",
    "config",
    "demo",
    "doctor",
    "experiments",
    "export",
    "guard",
    "handoff",
    "insights",
    "mcp",
    "optimize",
    "privacy",
    "rebuild",
    "receipt",
    "recap",
    "regression",
    "resource",
    "review",
    "setup-prompt",
    "show",
    "stats",
    "stop",
    "sync",
    "top",
    "traces",
    "ui",
    "upgrade",
    "verify",
    "why",
}
EXPECTED_GROUP_COMMANDS = {
    "adapter": {"doctor", "new"},
    "archive": {"export", "import", "inspect"},
    "config": {"get", "list", "set", "unset"},
    "experiments": {"ls", "revert"},
    "export": {"session"},
    "mcp": {"install"},
    "optimize": {"evaluate", "export-effects", "llm-preview", "llm-run", "revert"},
    "regression": {
        "compare",
        "create",
        "delete",
        "export",
        "import",
        "ls",
        "run",
        "show",
        "validate",
    },
    "traces": {"ls", "show"},
    "verify": {"next"},
}
EXPECTED_OWNERS = {
    "check": "server.cli_commands.operations",
    "guard": "server.cli_commands.operations",
    "handoff": "server.cli_commands.operations",
    "privacy": "server.cli_commands.operations",
    "receipt": "server.cli_commands.operations",
    "recap": "server.cli_commands.operations",
    "resource": "server.cli_commands.operations",
    "review": "server.cli_commands.operations",
    "stats": "server.cli_commands.operations",
    "top": "server.cli_commands.operations",
    "ui": "server.cli_commands.operations",
    "why": "server.cli_commands.operations",
}


def test_root_cli_surface_and_domain_ownership_are_stable() -> None:
    command = get_command(cli.app)

    assert set(command.commands) == EXPECTED_TOP_LEVEL
    for group, expected in EXPECTED_GROUP_COMMANDS.items():
        assert set(command.commands[group].commands) == expected
    for name, module in EXPECTED_OWNERS.items():
        assert command.commands[name].callback.__module__ == module


def test_action_group_is_generated_from_the_registry() -> None:
    command = get_command(cli.app)
    action_names = {entry.name for entry in cli.build_manifest()}

    assert set(command.commands["action"].commands) == action_names


def test_compatibility_options_keep_names_and_short_aliases() -> None:
    command = get_command(cli.app)

    ui_options = {option.name: set(option.opts) for option in command.commands["ui"].params}
    assert ui_options["port"] == {"--port", "-p"}
    assert ui_options["open_browser"] == {"--open"}
    assert {"host", "token", "workspace"} <= set(ui_options)

    optimize = command.commands["optimize"]
    export_effects = optimize.commands["export-effects"]
    options = {option.name: set(option.opts) for option in export_effects.params}
    assert options["output"] == {"--output", "-o"}


def test_render_helpers_remain_importable_from_server_cli() -> None:
    assert callable(cli._render_money_slide)
    assert callable(cli._render_recap)
    assert callable(cli._render_budget_stats)
    assert callable(cli._render_sync_next_step)
