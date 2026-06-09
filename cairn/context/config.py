"""Context scan configuration from cairn.toml or defaults."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cairn.loader.toml import load_cairn_toml

DEFAULT_INCLUDES: tuple[str, ...] = (
    "**/*.md",
    "**/*.{py,ts,js,tsx,jsx,go,rs,toml,yaml,yml,json}",
)
DEFAULT_EXCLUDES: tuple[str, ...] = (
    ".cairn/**",
    ".git/**",
    ".venv/**",
    "node_modules/**",
    "outputs/**",
    "**/__pycache__/**",
    ".pytest_cache/**",
)


@dataclass(frozen=True)
class ContextConfig:
    include: tuple[str, ...]
    exclude: tuple[str, ...]


def load_context_config(project_root: Path) -> ContextConfig:
    """Load include/exclude patterns from cairn.toml sources or defaults."""
    toml_path = project_root / "cairn.toml"
    if not toml_path.is_file():
        return ContextConfig(include=DEFAULT_INCLUDES, exclude=DEFAULT_EXCLUDES)

    parsed = load_cairn_toml(toml_path)
    includes: list[str] = []
    excludes: list[str] = list(DEFAULT_EXCLUDES)
    for section in parsed.sources.values():
        includes.extend(section.include)
        excludes.extend(section.exclude)
    if not includes:
        includes.extend(DEFAULT_INCLUDES)
    return ContextConfig(
        include=tuple(dict.fromkeys(includes)),
        exclude=tuple(dict.fromkeys(excludes)),
    )
