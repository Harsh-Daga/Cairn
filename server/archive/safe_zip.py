"""Bounded, path-safe ZIP reading for Cairn archives (ADR-10)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from server.archive.schema import ALLOWED_MEMBERS

# Workspace archives are larger than regression zips but still bounded.
_MAX_MEMBERS = 32
_MAX_UNCOMPRESSED = 256 * 1024 * 1024
_MAX_MEMBER = 64 * 1024 * 1024
_MAX_RATIO = 100  # compressed bomb heuristic when compressed size > 0


class ArchiveZipError(ValueError):
    """Raised when an archive ZIP fails safety or schema checks."""


def safe_read_members(
    archive: Path,
    *,
    allowed: frozenset[str] = ALLOWED_MEMBERS,
    require: frozenset[str] | None = None,
) -> dict[str, bytes]:
    """Read allowlisted ZIP members with traversal/bomb/symlink defenses."""
    archive = archive.expanduser().resolve()
    if not archive.is_file():
        raise ArchiveZipError(f"archive not found: {archive}")
    if archive.is_symlink():
        raise ArchiveZipError(f"archive is symlink: {archive}")

    out: dict[str, bytes] = {}
    total = 0
    seen: set[str] = set()
    with zipfile.ZipFile(archive, "r") as zf:
        infos = zf.infolist()
        if len(infos) > _MAX_MEMBERS:
            raise ArchiveZipError(f"too many archive members ({len(infos)})")
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            if name in seen:
                raise ArchiveZipError(f"duplicate member: {name}")
            seen.add(name)
            if name.startswith("/") or name.startswith("../") or "/../" in f"/{name}/":
                raise ArchiveZipError(f"path traversal rejected: {name}")
            if Path(name).is_absolute() or name.startswith("..") or "/" in name:
                raise ArchiveZipError(f"nested or absolute path rejected: {name}")
            mode = (info.external_attr >> 16) & 0o170000
            if mode == 0o120000:
                raise ArchiveZipError(f"symlink member rejected: {name}")
            if name not in allowed:
                raise ArchiveZipError(f"unexpected archive member: {name}")
            if info.file_size > _MAX_MEMBER:
                raise ArchiveZipError(f"member too large: {name}")
            if info.compress_size > 0 and info.file_size / info.compress_size > _MAX_RATIO:
                raise ArchiveZipError(f"suspicious compression ratio: {name}")
            total += info.file_size
            if total > _MAX_UNCOMPRESSED:
                raise ArchiveZipError("archive uncompressed size exceeds limit")
            out[name] = zf.read(info)

    required = require or frozenset({"manifest.json", "privacy.json"})
    missing = sorted(required - set(out))
    if missing:
        raise ArchiveZipError(f"missing required members: {', '.join(missing)}")
    # JSON sanity for every member.
    for name, raw in out.items():
        if name.endswith(".json"):
            json.loads(raw.decode("utf-8"))
    return out
