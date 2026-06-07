"""Source glob resolution (§6, R1)."""

from __future__ import annotations

import fnmatch
from pathlib import Path

from cairn.model.project import Project, SourceDef, SourceFile
from cairn.util.canonical import hash_bytes


def _excluded(rel: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch.fnmatch(rel, pattern) for pattern in patterns)


def _match_files(root: Path, source: SourceDef) -> list[Path]:
    all_paths: list[Path] = []
    for pattern in source.include:
        all_paths.extend(root.glob(pattern))
    matched = sorted({p.resolve() for p in all_paths if p.is_file()})
    filtered: list[Path] = []
    for path in matched:
        if not path.is_relative_to(root):
            continue
        rel = str(path.relative_to(root))
        if source.exclude and _excluded(rel, source.exclude):
            continue
        filtered.append(path)
    return filtered


def resolve_source_files(project: Project, source_name: str) -> list[SourceFile]:
    if source_name not in project.sources:
        msg = f"unknown source {source_name!r}"
        raise KeyError(msg)
    source = project.sources[source_name]
    files: list[SourceFile] = []
    for path in _match_files(project.root, source):
        data = path.read_bytes()
        text = data.decode("utf-8")
        rel = str(path.relative_to(project.root))
        files.append(
            SourceFile(
                path=rel,
                name=path.name,
                stem=path.stem,
                content=text,
                content_hash=hash_bytes(data),
            )
        )
    return files
