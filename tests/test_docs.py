"""Documentation and CLI surface consistency tests."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import typer

from server.api.actions import build_manifest
from server.cli import app
from server.mcp.install import AGENT_SETUP_URL, BOOTSTRAP_PROMPT

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CLI_DOC = ROOT / "docs" / "cli.md"
GEN_CLI = ROOT / "scripts" / "gen_cli_docs.py"

FENCED_CMD = re.compile(r"```(?:bash|sh|shell)?\n(.*?)```", re.DOTALL)
README_CLI_ROW = re.compile(r"^\|\s*`(cairn[^`]+)`\s*\|", re.MULTILINE)

DOCS_INDEX = [
    "docs/README.md",
    "docs/getting-started.md",
    "docs/concepts.md",
    "docs/ui-tour.md",
    "docs/cli.md",
    "docs/api.md",
    "docs/adapters.md",
    "docs/otlp.md",
    "docs/optimize.md",
    "docs/ci.md",
    "docs/configuration.md",
    "ACCURACY.md",
    "AGENT_SETUP.md",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
]

FORBIDDEN_DOC_PATTERNS = [
    re.compile(r"(?<![./])cairn/[a-z_]+"),  # retired module paths, not .cairn/
    re.compile(r"\brun_id\b"),
    re.compile(r"`cairn (init|validate|build|profile|behavior|outcomes|advanced)\b"),
    re.compile(r"docs/reference/"),
    re.compile(r"docs/guides/"),
    re.compile(r"docs/spec/"),
]

README_CLI_COMMANDS = [
    "cairn",
    "cairn sync",
    "cairn show ID",
    "cairn insights",
    "cairn optimize",
    "cairn experiments ls",
    "cairn check",
    "cairn export",
    "cairn mcp install",
    "cairn doctor",
    "cairn setup-prompt",
]


def _command_label(cmd: object) -> str | None:
    name = getattr(cmd, "name", None)
    if name:
        return str(name).replace("_", "-")
    callback = getattr(cmd, "callback", None)
    raw = getattr(callback, "__name__", "") or ""
    aliases = {"show_trace": "show", "setup_prompt": "setup-prompt", "mcp_install_cmd": "install"}
    return aliases.get(raw, raw.replace("_", "-")) or None


def _cli_command_names() -> set[str]:
    names: set[str] = set()
    for cmd in app.registered_commands:
        label = _command_label(cmd)
        if label:
            names.add(label)
    for group in app.registered_groups:
        gname = group.name or ""
        for sub in group.typer_instance.registered_commands:
            sublabel = _command_label(sub)
            if sublabel:
                names.add(f"{gname} {sublabel}".replace("_", "-"))
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
            if line.startswith(("curl ", "python", "pip", "uv ", "cd ", "sleep")):
                continue
            if line.startswith("cairn "):
                cmd = line.split("&", 1)[0].strip()
                if cmd == "cairn --version":
                    continue
                commands.append(cmd)
    return commands


def _command_exists(cmd: str, cli: set[str], actions: set[str]) -> bool:
    normalized = re.sub(r"<[^>]+>", "8787", cmd.replace("ID", "trace-id")).strip()
    if normalized == "cairn":
        return True
    body = normalized.removeprefix("cairn ").strip()
    parts = body.split()
    if not parts:
        return True
    top = parts[0].replace("_", "-")
    if top == "action":
        return len(parts) > 1 and parts[1].replace("-", "_") in actions
    if top == "mcp" and len(parts) > 1:
        return f"mcp {parts[1].replace('_', '-')}" in cli
    if top == "ui":
        return "ui" in cli
    if len(parts) > 1:
        key = f"{top} {parts[1].replace('_', '-')}"
        return key in cli or top in cli
    return top in cli


def test_readme_line_count() -> None:
    lines = README.read_text(encoding="utf-8").splitlines()
    assert len(lines) <= 250, f"README has {len(lines)} lines (max 250)"


def test_docs_index_links_resolve() -> None:
    missing = [rel for rel in DOCS_INDEX if not (ROOT / rel).is_file()]
    assert not missing, f"Missing docs: {missing}"


def test_readme_internal_links_resolve() -> None:
    text = README.read_text(encoding="utf-8")
    broken: list[str] = []
    for match in re.finditer(r"\]\(([^)]+)\)", text):
        target = match.group(1).split("#", 1)[0]
        if not target or target.startswith("http"):
            continue
        if not (ROOT / target).exists():
            broken.append(target)
    assert not broken, f"Broken README links: {broken}"


def test_documentation_internal_links_resolve() -> None:
    markdown = [
        README,
        ROOT / "AGENT_SETUP.md",
        ROOT / "CONTRIBUTING.md",
        *(ROOT / "docs").glob("*.md"),
    ]
    broken: list[str] = []
    for path in markdown:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\]\(([^)]+)\)", text):
            target = match.group(1).split("#", 1)[0]
            if not target or target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (path.parent / target).resolve().exists():
                broken.append(f"{path.relative_to(ROOT)} → {target}")
    assert not broken, "Broken documentation links:\n" + "\n".join(broken)


def test_readme_cli_table_commands_exist() -> None:
    cli = _cli_command_names()
    actions = _action_names()
    missing = [c for c in README_CLI_COMMANDS if not _command_exists(c, cli, actions)]
    assert not missing, f"README CLI commands missing from surface: {missing}"


def test_readme_cli_table_matches_list() -> None:
    text = README.read_text(encoding="utf-8")
    found = README_CLI_ROW.findall(text)
    assert found, "README CLI table not found"
    for cmd in found:
        base = cmd.replace(" ID", "").strip()
        assert base in README_CLI_COMMANDS or base.startswith("cairn ")


def test_cli_doc_is_current() -> None:
    before = CLI_DOC.read_text(encoding="utf-8")
    subprocess.run([sys.executable, str(GEN_CLI)], check=True, cwd=ROOT)
    after = CLI_DOC.read_text(encoding="utf-8")
    assert before == after, "docs/cli.md is stale — run: python scripts/gen_cli_docs.py"


def test_no_retired_release_terms_in_public_docs() -> None:
    paths = [README, ROOT / "docs", ROOT / "AGENT_SETUP.md", ROOT / "CHANGELOG.md"]
    violations: list[str] = []
    for base in paths:
        files = [base] if base.is_file() else base.rglob("*.md")
        for path in files:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for pattern in FORBIDDEN_DOC_PATTERNS:
                for match in pattern.finditer(text):
                    line = text[: match.start()].count("\n") + 1
                    violations.append(f"{path.relative_to(ROOT)}:{line}: {match.group()}")
    retired_release = re.compile(
        r"\b(?:v3|v4)\b|(?<![\d.])(?:0\.0\.1|0\.1\.0)(?![\d.])", re.IGNORECASE
    )
    for base in paths:
        files = [base] if base.is_file() else base.rglob("*.md")
        for path in files:
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8")
            for match in retired_release.finditer(text):
                line = text[: match.start()].count("\n") + 1
                violations.append(f"{path.relative_to(ROOT)}:{line}: {match.group()}")
    assert not violations, "Forbidden retired/stale doc terms:\n" + "\n".join(violations)


def test_agent_setup_bootstrap_url() -> None:
    assert AGENT_SETUP_URL in BOOTSTRAP_PROMPT
    assert "raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md" in BOOTSTRAP_PROMPT


def test_agent_setup_commands_exist() -> None:
    cli = _cli_command_names()
    actions = _action_names()
    missing = [
        c
        for c in _commands_in_markdown(ROOT / "AGENT_SETUP.md")
        if not _command_exists(c, cli, actions)
    ]
    assert not missing, f"Unknown AGENT_SETUP commands: {missing}"


def test_setup_prompt_cli() -> None:
    assert "setup-prompt" in _cli_command_names()


def test_cli_app_loads() -> None:
    assert isinstance(app, typer.Typer)
