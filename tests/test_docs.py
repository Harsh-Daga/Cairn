"""Documentation consistency checks."""

from __future__ import annotations

import re
from pathlib import Path

import cairn

ROOT = Path(__file__).parent.parent

_LEGACY_PRIMARY = re.compile(
    r"(?<![`/\w])cairn (?:ingest|render|doctor|sessions list|sessions replay|dashboard)\b"
)
_DOC_PATHS = (
    "docs/getting-started.md",
    "docs/concepts.md",
    "docs/reference/cli.md",
    "docs/guides/dashboard.md",
    "docs/guides/optimize.md",
    "docs/guides/agent-capture.md",
)


def test_readme_covers_primary_workflows() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    for snippet in (
        "cairn sync",
        "cairn stop",
        "cairn --foreground",
        "cairn optimize",
        "cairn check",
        "cairn mcp",
    ):
        assert snippet in text


def test_user_documentation_exists() -> None:
    for rel in (
        "docs/README.md",
        "docs/getting-started.md",
        "docs/concepts.md",
        "docs/guides/dashboard.md",
        "docs/guides/optimize.md",
        "docs/guides/agent-capture.md",
        "docs/reference/cli.md",
        "CONTRIBUTING.md",
        "LICENSE",
    ):
        assert (ROOT / rel).is_file(), rel


def test_docs_do_not_use_legacy_commands_as_primary() -> None:
    for rel in _DOC_PATHS:
        if not (ROOT / rel).is_file():
            continue
        text = (ROOT / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            if "Old command" in line or "Alias" in line or "| `" in line:
                continue
            assert _LEGACY_PRIMARY.search(line) is None, f"{rel}: {line}"


def test_release_version_matches_pyproject() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert match is not None, "version not found in pyproject.toml"
    assert cairn.__version__ == match.group(1)
