"""Documentation and CLI surface consistency tests."""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.parse import urlparse

import typer
import yaml

from server.api.actions import build_manifest
from server.cli import app
from server.mcp.install import AGENT_SETUP_URL, BOOTSTRAP_PROMPT

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
CLI_DOC = ROOT / "docs" / "cli.md"
GEN_CLI = ROOT / "scripts" / "gen_cli_docs.py"
INSTALL_REFERENCE_FILES = [
    README,
    ROOT / "docs" / "getting-started.md",
    ROOT / "AGENT_SETUP.md",
    ROOT / "scripts" / "install.sh",
    ROOT / "install.ps1",
    ROOT / "server" / "mcp" / "install.py",
]

FENCED_CMD = re.compile(r"```(?:bash|sh|shell)?\n(.*?)```", re.DOTALL)
README_CLI_ROW = re.compile(r"^\|\s*`(cairn[^`]*)`\s*\|", re.MULTILINE)
README_VERSION_BADGE = re.compile(r"img\.shields\.io/badge/version-([0-9]+\.[0-9]+\.[0-9]+)-")

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
    "docs/guard.md",
    "docs/recap.md",
    "docs/roadmap.md",
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
        if group.typer_instance.registered_callback is not None:
            names.add(gname.replace("_", "-"))
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


def _project_version() -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return str(project["version"])


def test_readme_version_badge_matches_pyproject() -> None:
    match = README_VERSION_BADGE.search(README.read_text(encoding="utf-8"))
    assert match is not None, "README must have an explicit version badge"
    assert match.group(1) == _project_version()


def test_release_version_sources_match_pyproject() -> None:
    version = _project_version()
    expected = {
        "server/__init__.py": f'__version__ = "{version}"',
        "CHANGELOG.md": f"## [{version}]",
        "docs/README.md": f"current {version} public beta",
        "docs/api.md": f'"version": "{version}"',
        "examples/e2e-demo/cairn.toml": f'version = "{version}"',
        "ui/package.json": f'"version": "{version}"',
        "ui/package-lock.json": f'"version": "{version}"',
    }
    mismatches = [
        path
        for path, marker in expected.items()
        if marker not in (ROOT / path).read_text(encoding="utf-8")
    ]
    assert not mismatches, f"Release version differs from pyproject.toml: {mismatches}"


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
    commands = README_CLI_ROW.findall(README.read_text(encoding="utf-8"))
    assert commands, "README CLI command table not found"
    missing = [c for c in commands if not _command_exists(c, cli, actions)]
    assert not missing, f"README CLI commands missing from surface: {missing}"


def test_all_readme_commands_exist() -> None:
    cli = _cli_command_names()
    actions = _action_names()
    table_commands = README_CLI_ROW.findall(README.read_text(encoding="utf-8"))
    fenced_commands = _commands_in_markdown(README)
    missing = [
        c for c in [*table_commands, *fenced_commands] if not _command_exists(c, cli, actions)
    ]
    assert not missing, f"Unknown README commands: {missing}"


def test_readme_comparison_examples_link_to_projects() -> None:
    after_heading = README.read_text(encoding="utf-8").split("## Why Cairn", 1)[1]
    section = after_heading.split("## Privacy", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("|")][2:]
    assert rows, "README comparison table not found"
    unlinked = [row.split("|")[2].strip() for row in rows if "](https://" not in row.split("|")[2]]
    assert not unlinked, f"Comparison examples must link to verifiable projects: {unlinked}"


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


def test_community_health_and_maintainer_artifacts_exist() -> None:
    required = (
        "GOVERNANCE.md",
        "MAINTAINERS.md",
        "CITATION.cff",
        ".github/CODEOWNERS",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/docs_report.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        "docs/maintainers/github-settings.md",
    )
    missing = [name for name in required if not (ROOT / name).is_file()]
    assert not missing

    citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert citation["version"] == pyproject["project"]["version"]
    assert citation["repository-code"] == "https://github.com/Harsh-Daga/Cairn"


def test_installers_are_fail_closed_and_uninstall_is_documented() -> None:
    shell = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")
    guide = (ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8")

    assert "sudo" not in shell
    assert "sudo" not in powershell.lower()
    assert "| sh" not in shell
    assert "| iex" not in powershell.lower()
    assert "cairn doctor || true" not in shell
    assert "uv tool uninstall cairn-workspace" in guide
    assert "retains project `.cairn/`" in guide
    assert "UV_INDEX_URL" in guide
    assert "--offline" in guide


def test_agent_setup_bootstrap_url() -> None:
    assert AGENT_SETUP_URL in BOOTSTRAP_PROMPT
    assert "raw.githubusercontent.com/Harsh-Daga/Cairn/main/AGENT_SETUP.md" in BOOTSTRAP_PROMPT


def test_cairn_raw_github_urls_reference_tracked_main_files() -> None:
    pattern = re.compile(
        r"https://raw\.githubusercontent\.com/Harsh-Daga/Cairn/main/([^\s)`\"'|]+)"
    )
    references: list[tuple[Path, str]] = []
    for source in INSTALL_REFERENCE_FILES:
        for relative in pattern.findall(source.read_text(encoding="utf-8")):
            references.append((source, relative))
    assert references, "No raw GitHub install references found"
    missing = [
        f"{source.relative_to(ROOT)} -> {relative}"
        for source, relative in references
        if not (ROOT / relative).is_file()
    ]
    assert not missing, "Raw GitHub URLs reference missing repository files: " + str(missing)


def test_script_downloads_use_audited_hosts_and_paths() -> None:
    script_url = re.compile(r"https://[^\s)`\"'|]+install\.(?:sh|ps1)")
    allowed = {
        ("raw.githubusercontent.com", "/Harsh-Daga/Cairn/main/scripts/install.sh"),
        ("raw.githubusercontent.com", "/Harsh-Daga/Cairn/main/install.ps1"),
        ("astral.sh", "/uv/install.sh"),
        ("astral.sh", "/uv/install.ps1"),
    }
    found = {
        (urlparse(url).hostname or "", urlparse(url).path)
        for source in INSTALL_REFERENCE_FILES
        for url in script_url.findall(source.read_text(encoding="utf-8"))
    }
    assert found >= {
        ("raw.githubusercontent.com", "/Harsh-Daga/Cairn/main/scripts/install.sh"),
        ("raw.githubusercontent.com", "/Harsh-Daga/Cairn/main/install.ps1"),
    }
    assert not found - allowed, f"Unaudited script download URLs: {sorted(found - allowed)}"


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
