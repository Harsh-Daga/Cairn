"""Checksummed managed-block writer for approved instruction files."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

MANAGED_START = "<!-- cairn:begin"
MANAGED_END = "<!-- cairn:end -->"
_BLOCK_HEADING = "## Cairn agent guide"
_START_RE = re.compile(r"<!-- cairn:begin sha256=([0-9a-f]{64}) -->")
_ALLOWED_TARGETS = (Path("AGENTS.md"), Path("CLAUDE.md"), Path(".cursor/rules"))


@dataclass(frozen=True)
class ManagedEntry:
    kind: str
    entry_id: str
    content: str
    confidence: float = 0.8

    def render(self) -> str:
        marker = f"<!-- cairn:entry {self.kind}/{self.entry_id} conf={self.confidence:g} -->"
        return f"- {self.content}  {marker}"


class BlockError(ValueError):
    """Managed block or target is invalid."""


class BlockConflictError(BlockError):
    """The managed block changed after Cairn last wrote it."""


def has_block(text: str) -> bool:
    return MANAGED_START in text and MANAGED_END in text


def _validate_target(target: Path, repo_root: Path) -> None:
    root = repo_root.resolve()
    lexical_root = Path(os.path.abspath(repo_root))
    lexical_target = Path(os.path.abspath(target))
    resolved = target.resolve(strict=False)
    allowed = {lexical_root / relative for relative in _ALLOWED_TARGETS}
    resolved_inside_root = resolved == root or root in resolved.parents
    if lexical_target not in allowed or target.is_symlink() or not resolved_inside_root:
        choices = ", ".join(str(path) for path in _ALLOWED_TARGETS)
        msg = f"Cairn can only manage {choices}; refused target: {target}"
        raise BlockError(msg)


def _validate_backup_location(backup_path: Path, repo_root: Path, *, directory: bool) -> None:
    expected = (repo_root.resolve() / ".cairn" / "backups").resolve(strict=False)
    candidate = backup_path.resolve(strict=False) if directory else backup_path.parent.resolve()
    if candidate != expected or (not directory and backup_path.is_symlink()):
        raise BlockError(f"Cairn backups must stay inside {expected}")


def _locate_block(text: str) -> tuple[int, int]:
    starts = [m.start() for m in re.finditer(re.escape(MANAGED_START), text)]
    ends = [m.start() for m in re.finditer(re.escape(MANAGED_END), text)]
    if len(starts) != 1 or len(ends) != 1:
        raise BlockError("managed block markers are unbalanced")
    start, end = starts[0], ends[0]
    if end < start:
        raise BlockError("managed block end precedes start")
    block_end = end + len(MANAGED_END)
    if text.startswith("\n", block_end):
        block_end += 1
    return start, block_end


def _verified_block(text: str) -> tuple[int, int]:
    start, end = _locate_block(text)
    marker = _START_RE.match(text, start)
    if marker is None:
        raise BlockConflictError(
            "managed block has no valid checksum; preserve it and resolve the conflict manually"
        )
    body_start = marker.end()
    if not text.startswith("\n", body_start):
        raise BlockConflictError("managed block start marker was edited")
    body_start += 1
    body_end = text.find(MANAGED_END, body_start, end)
    if body_end < 0:
        raise BlockConflictError("managed block end marker was edited")
    body = text[body_start:body_end]
    actual = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(marker.group(1), actual):
        raise BlockConflictError(
            "managed block was edited after Cairn wrote it; refusing to overwrite user changes"
        )
    return start, end


def serialize_block(entries: list[ManagedEntry]) -> str:
    body_lines = [_BLOCK_HEADING, *(entry.render() for entry in entries)]
    body = "\n".join(body_lines) + "\n"
    checksum = hashlib.sha256(body.encode("utf-8")).hexdigest()
    return f"{MANAGED_START} sha256={checksum} -->\n{body}{MANAGED_END}\n"


def _separator(text: str) -> str:
    if not text or text.endswith("\n\n"):
        return ""
    if text.endswith("\n"):
        return "\n"
    return "\n\n"


def ensure_block(text: str, entries: list[ManagedEntry]) -> str:
    """Return text with only Cairn's verified fenced block added or replaced."""
    block = serialize_block(entries)
    if not text:
        return block
    if MANAGED_START in text or MANAGED_END in text:
        start, end = _verified_block(text)
        return text[:start] + block + text[end:]
    return text + _separator(text) + block


def _backup_path(backup_dir: Path, target: Path, backup_key: str | None, exists: bool) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    key = re.sub(r"[^A-Za-z0-9_-]", "_", backup_key) if backup_key else "apply"
    missing = "" if exists else ".missing"
    return backup_dir / f"{target.name}.{key}.{stamp}{missing}.bak"


def apply_entries(
    target: Path,
    entries: list[ManagedEntry],
    *,
    backup_dir: Path,
    repo_root: Path,
    backup_key: str | None = None,
) -> Path:
    """Safely write entries inside an approved managed block and return its backup."""
    _validate_target(target, repo_root)
    _validate_backup_location(backup_dir, repo_root, directory=True)
    existed = target.is_file()
    original = target.read_text(encoding="utf-8") if existed else ""
    updated = ensure_block(original, entries)

    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = _backup_path(backup_dir, target, backup_key, existed)
    if existed:
        shutil.copy2(target, backup)
    else:
        backup.write_bytes(b"")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(updated, encoding="utf-8")
    return backup


def find_backup(backup_dir: Path, target: Path, *, backup_key: str) -> Path | None:
    """Return the newest backup created for one apply operation."""
    safe_key = re.sub(r"[^A-Za-z0-9_-]", "_", backup_key)
    backups = sorted(backup_dir.glob(f"{target.name}.{safe_key}.*.bak"))
    return backups[-1] if backups else None


def revert_from_backup(target: Path, backup: Path, *, repo_root: Path) -> None:
    """Restore only Cairn's block, preserving user edits elsewhere in the file."""
    _validate_target(target, repo_root)
    _validate_backup_location(backup, repo_root, directory=False)
    if not backup.is_file():
        raise BlockError(f"backup does not exist: {backup}")

    current = target.read_text(encoding="utf-8") if target.is_file() else ""
    if not has_block(current):
        raise BlockConflictError("managed block is missing; refusing to overwrite the target")
    current_start, current_end = _verified_block(current)

    if ".missing.bak" in backup.name:
        restored = current[:current_start] + current[current_end:]
        if not restored:
            target.unlink()
        else:
            target.write_text(restored, encoding="utf-8")
        return

    previous = backup.read_text(encoding="utf-8")
    if has_block(previous):
        previous_start, previous_end = _verified_block(previous)
        previous_block = previous[previous_start:previous_end]
        restored = current[:current_start] + previous_block + current[current_end:]
    else:
        separator = _separator(previous)
        prefix = current[:current_start]
        if separator and prefix.endswith(separator):
            prefix = prefix[: -len(separator)]
        restored = prefix + current[current_end:]
    target.write_text(restored, encoding="utf-8")
