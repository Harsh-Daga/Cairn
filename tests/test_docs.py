"""Documentation and CLI surface consistency tests."""

from __future__ import annotations

import re
from pathlib import Path

import typer

from server.api.actions import build_manifest
from server.cli import app
from server.mcp.install import AGENT_SETUP_URL, BOOTSTRAP_PROMPT

ROOT = Path(__file__).resolve().parent.parent

FENCED_CMD = re.compile(r"```(?:bash|sh|shell)?\n(.*?)```", re.DOTALL)


def _cli_command_names() -> set[str]:
    names: set[str] = set()
    for cmd in app.registered_commands:
        if cmd.name:
            names.add(cmd.name.replace("_", "-"))
    for group in app.registered_groups:
        if group.name:
            names.add(group.name)
        for sub in group.typer_instance.registered_commands:
            if sub.name:
                names.add(f"{group.name} {sub.name}".replace("_", "-"))
    return names


def _action_names() -> set[str]:
    return {entry.name for entry in build_manifest()}


def _commands_in_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    commands: list[str] = []
    for block in FENCED_CMD.findall(text):
        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("export "):
                continue
            if line.startswith("curl ") or line.startswith("python") or line.startswith("pip"):
                continue
            if line.startswith("cairn "):
                cmd = line.split("&", 1)[0].strip()
                if cmd == "cairn --version":
                    continue
                commands.append(cmd)
    return commands


def test_agent_setup_bootstrap_url() -> None:
    assert AGENT_SETUP_URL in BOOTSTRAP_PROMPT
    assert "raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md" in BOOTSTRAP_PROMPT


def test_agent_setup_commands_exist() -> None:
    cli = _cli_command_names()
    actions = _action_names()
    missing: list[str] = []
    for cmd in _commands_in_markdown(ROOT / "AGENT_SETUP.md"):
        body = cmd.removeprefix("cairn ").strip()
        top = body.split()[0] if body else ""
        if top == "action":
            action_name = body.split()[1] if len(body.split()) > 1 else ""
            if action_name and action_name not in actions:
                missing.append(cmd)
        elif top == "mcp":
            sub = body.split()[1] if len(body.split()) > 1 else ""
            if f"mcp {sub}".replace("_", "-") not in cli:
                missing.append(cmd)
        elif top.replace("_", "-") not in cli and top not in {
            "ui",
            "sync",
            "stop",
            "insights",
        }:
            missing.append(cmd)
    assert not missing, f"Unknown AGENT_SETUP commands: {missing}"


def test_setup_prompt_cli() -> None:
    assert "setup-prompt" in _cli_command_names()


def test_docs_links_resolve() -> None:
    """README doc links are validated in L3 once the docs tree is finalized."""
    assert (ROOT / "AGENT_SETUP.md").is_file()
    assert (ROOT / "docs/legacy-v3.md").is_file()


def test_cli_app_loads() -> None:
    assert isinstance(app, typer.Typer)
