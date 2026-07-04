"""Managed-block writer for multi-target apply."""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MANAGED_START = "<!-- cairn:begin -->"
MANAGED_END = "<!-- cairn:end -->"
_BLOCK_HEADING = "## Cairn agent guide"


@dataclass(frozen=True)
class ManagedEntry:
    kind: str
    entry_id: str
    content: str
    confidence: float = 0.8

    def render(self) -> str:
        marker = f"<!-- cairn:entry {self.kind}/{self.entry_id} conf={self.confidence:g} -->"
        return f"- {self.content}  {marker}"


class BlockError(Exception):
    """Managed block markers invalid."""


def has_block(text: str) -> bool:
    return MANAGED_START in text and MANAGED_END in text


def _locate_block(text: str) -> tuple[int, int]:
    starts = [m.start() for m in re.finditer(re.escape(MANAGED_START), text)]
    ends = [m.start() for m in re.finditer(re.escape(MANAGED_END), text)]
    if len(starts) != 1 or len(ends) != 1:
        raise BlockError("managed block markers are unbalanced")
    start, end = starts[0], ends[0]
    if end < start:
        raise BlockError("managed block end precedes start")
    return start, end + len(MANAGED_END)


def serialize_block(entries: list[ManagedEntry]) -> str:
    lines = [MANAGED_START, _BLOCK_HEADING]
    for entry in entries:
        lines.append(entry.render())
    lines.append(MANAGED_END)
    return "\n".join(lines) + "\n"


def ensure_block(text: str, entries: list[ManagedEntry]) -> str:
    block = serialize_block(entries)
    if not text.strip():
        return block
    if has_block(text):
        start, end = _locate_block(text)
        return text[:start] + block + text[end:]
    return text.rstrip() + "\n\n" + block


def apply_entries(target: Path, entries: list[ManagedEntry], *, backup_dir: Path) -> Path:
    """Write entries into managed block; return backup path."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    original = target.read_text(encoding="utf-8") if target.is_file() else ""
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    backup = backup_dir / f"{target.name}.{stamp}.bak"
    if target.is_file():
        shutil.copy2(target, backup)
    updated = ensure_block(original, entries)
    target.write_text(updated, encoding="utf-8")
    return backup


def revert_from_backup(target: Path, backup: Path) -> None:
    """Restore target file from backup."""
    target.write_text(backup.read_text(encoding="utf-8"), encoding="utf-8")
