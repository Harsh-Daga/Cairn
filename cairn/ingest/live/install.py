"""`cairn live install` — hooks plus tail watchers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cairn.ingest.watch import WatchSource, install_watch, uninstall_watch, watch_status

LiveSource = Literal["claude-code", "codex", "cursor", "hermes", "all"]
TailSource = Literal["cursor", "hermes"]


@dataclass(frozen=True)
class LiveInstallStatus:
    project_root: Path
    watch_installed: tuple[str, ...]
    tail_watchers: tuple[TailSource, ...]
    install_record_path: Path


def install_live(project_root: Path, *, source: LiveSource = "all") -> LiveInstallStatus:
    root = project_root.resolve()
    watch_installed: tuple[str, ...] = ()
    if source == "all":
        hooks: tuple[WatchSource, ...] = ("claude-code", "codex")
        status = install_watch(root, sources=hooks)
        watch_installed = status.installed
    elif source == "claude-code":
        status = install_watch(root, sources=("claude-code",))
        watch_installed = status.installed
    elif source == "codex":
        status = install_watch(root, sources=("codex",))
        watch_installed = status.installed

    tail_watchers: tuple[TailSource, ...]
    if source == "all":
        tail_watchers = ("cursor", "hermes")
    elif source in ("cursor", "hermes"):
        tail_watchers = (source,)
    else:
        tail_watchers = ()

    record_path = root / ".cairn" / "watch" / "install.json"
    record: dict[str, object] = {}
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
    record["live_install"] = True
    record["tail_watchers"] = list(tail_watchers)
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    return LiveInstallStatus(
        project_root=root,
        watch_installed=watch_installed,
        tail_watchers=tail_watchers,
        install_record_path=record_path,
    )


def uninstall_live(project_root: Path) -> bool:
    root = project_root.resolve()
    had_live = live_install_status(root) is not None
    uninstall_watch(root)
    tail_state = root / ".cairn" / "watch" / "tail-state.json"
    if tail_state.is_file():
        tail_state.unlink()
    record_path = root / ".cairn" / "watch" / "install.json"
    if record_path.is_file():
        record_path.unlink()
    return had_live


def live_install_status(project_root: Path) -> LiveInstallStatus | None:
    root = project_root.resolve()
    record_path = root / ".cairn" / "watch" / "install.json"
    if not record_path.is_file():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    if not record.get("live_install"):
        return None
    tail_raw = record.get("tail_watchers", [])
    tail_watchers = tuple(str(s) for s in tail_raw) if isinstance(tail_raw, list) else ()
    watch = watch_status(root)
    return LiveInstallStatus(
        project_root=root,
        watch_installed=watch.installed if watch else (),
        tail_watchers=tail_watchers,  # type: ignore[arg-type]
        install_record_path=record_path,
    )
