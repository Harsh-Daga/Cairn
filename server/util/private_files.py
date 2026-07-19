"""Restrictive local file helpers for Cairn-owned sensitive data."""

from __future__ import annotations

import os
import secrets
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from io import TextIOWrapper
from pathlib import Path


def ensure_private_dir(path: Path) -> Path:
    """Create a directory and restrict it to the current user where supported."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != "nt":
        path.chmod(0o700)
    return path


def write_private_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Atomically replace a text file without a permissive intermediate."""
    ensure_private_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding) as handle:
            descriptor = -1
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    if os.name != "nt":
        path.chmod(0o600)


@contextmanager
def private_text_writer(
    path: Path,
    *,
    encoding: str = "utf-8",
) -> Iterator[TextIOWrapper]:
    """Atomically stream a private text file without buffering it in memory."""
    ensure_private_dir(path.parent)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding=encoding) as handle:
            descriptor = -1
            yield handle
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    if os.name != "nt":
        path.chmod(0o600)


def ensure_private_file(path: Path) -> Path:
    """Create a current-user-only file without truncating existing content."""
    ensure_private_dir(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    os.close(descriptor)
    if os.name != "nt":
        path.chmod(0o600)
    return path


def append_private_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Append one record while keeping the containing state owner-only."""
    ensure_private_dir(path.parent)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(descriptor, text.encode(encoding))
    finally:
        os.close(descriptor)
    if os.name != "nt":
        path.chmod(0o600)


def restrict_sqlite_files(db_path: Path) -> None:
    """Restrict a SQLite database and any currently present sidecars."""
    if os.name == "nt":
        return
    ensure_private_dir(db_path.parent)
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{db_path}{suffix}")
        if candidate.exists():
            candidate.chmod(0o600)


def restrict_tree(path: Path) -> None:
    """Restrict an existing Cairn export tree to its owner."""
    if os.name == "nt":
        return
    if path.is_symlink():
        msg = f"Refusing to change permissions through symlink: {path}"
        raise ValueError(msg)
    if path.is_dir():
        path.chmod(0o700)
        for child in path.iterdir():
            restrict_tree(child)
    elif path.exists():
        path.chmod(0o600)


def permissive_paths(path: Path) -> list[tuple[Path, int, int]]:
    """Return Cairn-owned paths whose Unix mode is broader than owner-only."""
    if os.name == "nt" or not path.exists() or path.is_symlink():
        return []
    issues: list[tuple[Path, int, int]] = []
    candidates = [path, *path.rglob("*")]
    for candidate in candidates:
        if candidate.is_symlink() or not candidate.exists():
            continue
        actual = stat.S_IMODE(candidate.stat().st_mode)
        expected = 0o700 if candidate.is_dir() else 0o600
        if actual & ~expected:
            issues.append((candidate, actual, expected))
    return issues
