"""CDN-grep test — fails if any CDN URLs appear in the codebase."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CDN_PATTERNS = [
    re.compile(r"https://cdn", re.IGNORECASE),
    re.compile(r"https://fonts\.googleapis\.com", re.IGNORECASE),
    re.compile(r"https://cdn\.jsdelivr", re.IGNORECASE),
    re.compile(r"https://unpkg\.com", re.IGNORECASE),
]

SCAN_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".html", ".md"}
SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "dist-test",
    "_legacy",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _should_scan(path: Path) -> bool:
    if path.name == "test_cdn_grep.py":
        return False
    if path.suffix not in SCAN_EXTENSIONS:
        return False
    return not any(part in SKIP_DIRS for part in path.parts)


def test_no_cdn_urls_in_codebase() -> None:
    violations: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or not _should_scan(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in CDN_PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                violations.append(f"{path.relative_to(ROOT)}:{line_no}: {match.group()}")
    assert not violations, "CDN URLs found:\n" + "\n".join(violations)
