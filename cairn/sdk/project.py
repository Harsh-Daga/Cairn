"""Project handle for the public SDK."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cairn.ingest.project_paths import resolve_git_root
from cairn.loader.toml import load_project
from cairn.model.project import Project as ProjectModel


@dataclass(frozen=True)
class Run:
    """Reference to a completed capture session or provider workflow run."""

    project_root: Path
    run_id: str
    kind: Literal["capture", "provider"] = "provider"
    session_id: str | None = None
    workflow_ref: str | None = None


class Project:
    """Opened Cairn project workspace."""

    def __init__(self, root: Path) -> None:
        self.root = resolve_git_root(root) or root.resolve()
        self._model = load_project(self.root)

    @classmethod
    def open(cls, path: str | Path = ".") -> Project:
        return cls(Path(path))

    @property
    def name(self) -> str:
        return self._model.name

    @property
    def model(self) -> ProjectModel:
        return self._model
