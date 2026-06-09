"""File tail watchers for Cursor and Hermes live capture."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cairn.ingest.parsers.cursor import parse_transcript_file
from cairn.ingest.parsers.hermes import parse_session_file
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter

TailSource = Literal["cursor", "hermes"]


@dataclass(frozen=True)
class TailTarget:
    source: TailSource
    path: Path


def discover_tail_paths(project_root: Path) -> tuple[TailTarget, ...]:
    """Find Cursor/Hermes transcript paths relevant to the project."""
    root = resolve_git_root(project_root) or project_root.resolve()
    targets: list[TailTarget] = []

    cursor_dir = Path.home() / ".cursor" / "projects"
    if cursor_dir.is_dir():
        for jsonl in sorted(cursor_dir.rglob("agent-transcripts/**/*.jsonl")):
            if _path_under_repo(jsonl, root):
                targets.append(TailTarget("cursor", jsonl))

    hermes_dir = Path.home() / ".hermes" / "sessions"
    if hermes_dir.is_dir():
        for session_file in sorted(hermes_dir.glob("session_*.json")):
            targets.append(TailTarget("hermes", session_file))

    return tuple(targets)


def _path_under_repo(path: Path, repo_root: Path) -> bool:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return True


class TailWatcher:
    """Poll transcript files and ingest new content."""

    def __init__(self, project_root: Path, *, sources: tuple[TailSource, ...]) -> None:
        self.project_root = project_root.resolve()
        self.sources = sources
        self._state_path = self.project_root / ".cairn" / "watch" / "tail-state.json"
        self._offsets: dict[str, int] = {}
        self._load_state()

    def _load_state(self) -> None:
        if not self._state_path.is_file():
            return
        data = json.loads(self._state_path.read_text(encoding="utf-8"))
        offsets = data.get("offsets", {})
        if isinstance(offsets, dict):
            self._offsets = {str(k): int(v) for k, v in offsets.items()}

    def save_state(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"offsets": self._offsets, "updated_at": time.time()}
        self._state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    def poll_once(self) -> int:
        """Ingest incremental changes; return number of files updated."""
        updated = 0
        writer = CaptureWriter(self.project_root)
        try:
            for target in discover_tail_paths(self.project_root):
                if target.source not in self.sources:
                    continue
                key = str(target.path)
                size = target.path.stat().st_size if target.path.is_file() else 0
                last = self._offsets.get(key, 0)
                if size <= last:
                    continue
                if target.source == "cursor":
                    cursor_parsed = parse_transcript_file(
                        target.path, repo_root=self.project_root
                    )
                    if cursor_parsed is not None:
                        writer.ingest_cursor_session(cursor_parsed)
                else:
                    hermes_parsed = parse_session_file(target.path, repo_root=self.project_root)
                    if hermes_parsed is not None:
                        writer.ingest_hermes_session(hermes_parsed)
                self._offsets[key] = size
                updated += 1
        finally:
            writer.close()
        if updated:
            self.save_state()
        return updated

    def run_loop(self, *, interval_s: float = 2.0, stop_event: object | None = None) -> None:
        while True:
            self.poll_once()
            if stop_event is not None and getattr(stop_event, "is_set", lambda: False)():
                break
            time.sleep(interval_s)
