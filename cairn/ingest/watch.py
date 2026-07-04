"""`cairn watch` — install capture hooks for Claude Code and Codex (R19.9)."""

from __future__ import annotations

import contextlib
import json
import shutil
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

WatchSource = Literal["claude-code", "codex"]

CAIRN_WATCH_BEGIN = "# >>> cairn watch >>>"
CAIRN_WATCH_END = "# <<< cairn watch <<<"

# Extra filesystem paths the ingest watcher should observe in addition to the
# per-agent session roots. ``state.vscdb`` is Cursor's canonical source (§2.2),
# so a future file watcher must tail it to pick up live composer updates.
WATCH_EXTRA_PATHS: tuple[str, ...] = (
    "Library/Application Support/Cursor/User/globalStorage/state.vscdb",
    ".config/Cursor/User/globalStorage/state.vscdb",
    "AppData/Roaming/Cursor/User/globalStorage/state.vscdb",
)


def watched_vscdb_paths(home: Path | None = None) -> list[Path]:
    """Absolute ``state.vscdb`` paths that exist on this host."""
    home = home or Path.home()
    return [home / rel for rel in WATCH_EXTRA_PATHS if (home / rel).exists()]


_CLAUDE_EVENTS: tuple[tuple[str, str | None], ...] = (
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("PreToolUse", "Edit|Write|MultiEdit"),
    ("PostToolUse", "Edit|Write|MultiEdit|Bash"),
    ("Stop", None),
)

_CODEX_EVENTS: tuple[tuple[str, str | None], ...] = (
    ("SessionStart", "startup|resume|clear|compact"),
    ("UserPromptSubmit", None),
    ("PreToolUse", "apply_patch|Bash|Edit|Write"),
    ("PostToolUse", "apply_patch|Bash|Edit|Write"),
    ("Stop", None),
)


@dataclass(frozen=True)
class WatchStatus:
    project_root: Path
    installed: tuple[str, ...]
    install_record_path: Path
    backups: dict[str, str]
    hook_invocation: str | None = None


def resolve_cairn_executable() -> str:
    """Absolute ``cairn`` binary or ``python -m cairn`` prefix (no shell quotes)."""
    cairn_bin = shutil.which("cairn")
    if cairn_bin:
        return str(Path(cairn_bin).resolve())
    return f"{Path(sys.executable).resolve()} -m cairn"


def resolve_hook_invocation() -> str:
    """Return shell-quoted ``cairn`` invocation prefix (Claude JSON hooks)."""
    exe = resolve_cairn_executable()
    if " " in exe:
        return f'"{exe}"'
    return exe


def resolve_hook_command(event: str, source: WatchSource) -> str:
    """Build hook command for Claude JSON hooks (minimal PATH shells)."""
    return f"{resolve_hook_invocation()} hook --event {event} --source {source}"


def resolve_hook_command_toml(event: str, source: WatchSource) -> str:
    """Build hook command as a valid TOML basic string (Codex config)."""
    exe = resolve_cairn_executable()
    if " " in exe:
        command = f'"{exe}" hook --event {event} --source {source}'
    else:
        command = f"{exe} hook --event {event} --source {source}"
    return _toml_basic_string(command)


def _toml_basic_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def install_watch(
    project_root: Path,
    *,
    sources: tuple[WatchSource, ...] = ("claude-code", "codex"),
) -> WatchStatus:
    root = project_root.resolve()
    watch_dir = root / ".cairn" / "watch"
    watch_dir.mkdir(parents=True, exist_ok=True)
    record_path = watch_dir / "install.json"
    backups: dict[str, str] = {}
    installed: list[str] = []
    hook_invocation = resolve_hook_invocation()

    if "claude-code" in sources:
        target = root / ".claude" / "settings.local.json"
        backup = watch_dir / "claude-settings.bak"
        _backup_file(target, backup)
        backups["claude_settings"] = str(backup)
        _install_claude_hooks(target, source="claude-code")
        installed.append("claude-code")

    if "codex" in sources:
        project_codex = root / ".codex" / "config.toml"
        user_codex = Path.home() / ".codex" / "config.toml"
        if project_codex.parent.exists() or not user_codex.is_file():
            target = project_codex
        else:
            target = user_codex
        if not target.parent.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        backup = watch_dir / "codex-config.bak"
        _backup_file(target, backup)
        backups["codex_config"] = str(backup)
        _install_codex_hooks(target, source="codex")
        installed.append("codex")

    record = {
        "installed": installed,
        "backups": backups,
        "project_root": str(root),
        "hook_invocation": hook_invocation,
    }
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return WatchStatus(
        project_root=root,
        installed=tuple(installed),
        install_record_path=record_path,
        backups=backups,
        hook_invocation=hook_invocation,
    )


def uninstall_watch(project_root: Path) -> bool:
    record_path = project_root.resolve() / ".cairn" / "watch" / "install.json"
    if not record_path.is_file():
        return False
    record = json.loads(record_path.read_text(encoding="utf-8"))
    backups = record.get("backups", {})
    if isinstance(backups, dict):
        claude_bak = backups.get("claude_settings")
        if isinstance(claude_bak, str):
            _restore_backup(Path(claude_bak), project_root / ".claude" / "settings.local.json")
        codex_bak = backups.get("codex_config")
        if isinstance(codex_bak, str):
            codex_target = _codex_config_path(project_root)
            _restore_backup(Path(codex_bak), codex_target)
    record_path.unlink()
    return True


def watch_status(project_root: Path) -> WatchStatus | None:
    record_path = project_root.resolve() / ".cairn" / "watch" / "install.json"
    if not record_path.is_file():
        return None
    record = json.loads(record_path.read_text(encoding="utf-8"))
    installed = record.get("installed", [])
    backups = record.get("backups", {})
    hook_invocation = record.get("hook_invocation")
    return WatchStatus(
        project_root=project_root.resolve(),
        installed=tuple(str(s) for s in installed) if isinstance(installed, list) else (),
        install_record_path=record_path,
        backups={str(k): str(v) for k, v in backups.items()} if isinstance(backups, dict) else {},
        hook_invocation=str(hook_invocation) if isinstance(hook_invocation, str) else None,
    )


def _backup_file(target: Path, backup: Path) -> None:
    if target.is_file():
        shutil.copy2(target, backup)
    else:
        backup.write_text("", encoding="utf-8")


def _restore_backup(backup: Path, target: Path) -> None:
    if backup.is_file() and backup.stat().st_size > 0:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
    elif target.is_file():
        target.unlink()


def _build_claude_hooks(source: WatchSource) -> dict[str, Any]:
    hooks: dict[str, Any] = {}
    for event, matcher in _CLAUDE_EVENTS:
        entry: dict[str, Any] = {
            "hooks": [
                {
                    "type": "command",
                    "command": resolve_hook_command(event, source),
                }
            ]
        }
        if matcher is not None:
            entry["matcher"] = matcher
        hooks[event] = [entry]
    return hooks


def _build_codex_hooks_toml(source: WatchSource) -> str:
    lines = ["[features]", "hooks = true", ""]
    for event, matcher in _CODEX_EVENTS:
        lines.append(f"[[hooks.{event}]]")
        if matcher is not None:
            lines.append(f'matcher = "{matcher}"')
        lines.append(f"[[hooks.{event}.hooks]]")
        lines.append('type = "command"')
        lines.append(f"command = {resolve_hook_command_toml(event, source)}")
        lines.append("")
    return "\n".join(lines).strip()


def _install_claude_hooks(target: Path, *, source: WatchSource) -> None:
    data: dict[str, Any] = {}
    if target.is_file():
        data = json.loads(target.read_text(encoding="utf-8"))
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        hooks = {}
    hooks.update(_build_claude_hooks(source))
    data["hooks"] = hooks
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _extract_hooks_state(block: str) -> str:
    marker = "[hooks.state]"
    if marker not in block:
        return ""
    return block[block.index(marker) :].strip()


def _strip_cairn_watch_block(content: str) -> tuple[str, str]:
    """Remove the cairn watch block; preserve Codex ``[hooks.state]`` trust entries."""
    if CAIRN_WATCH_BEGIN not in content:
        return content, ""
    before, _, rest = content.partition(CAIRN_WATCH_BEGIN)
    middle, _, after = rest.partition(CAIRN_WATCH_END)
    hooks_state = _extract_hooks_state(middle)
    merged = (before.rstrip() + "\n" + after.lstrip()).strip()
    return merged, hooks_state


def _install_codex_hooks(target: Path, *, source: WatchSource) -> None:
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    existing, hooks_state = _strip_cairn_watch_block(existing)
    block = f"{CAIRN_WATCH_BEGIN}\n{_build_codex_hooks_toml(source)}\n{CAIRN_WATCH_END}\n"
    merged = existing.rstrip() + "\n\n" + block
    if hooks_state:
        merged = merged.rstrip() + "\n\n" + hooks_state + "\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(merged, encoding="utf-8")


def _codex_config_path(project_root: Path) -> Path:
    project_codex = project_root / ".codex" / "config.toml"
    if project_codex.is_file():
        return project_codex
    return Path.home() / ".codex" / "config.toml"


# ---------------------------------------------------------------------------
# Live ``state.vscdb`` tailing (§2.7G)
# ---------------------------------------------------------------------------


class VscdbWatcher:
    """Poll ``state.vscdb`` mtimes and invoke a callback after debounce."""

    def __init__(
        self,
        on_change: Any,
        *,
        paths: list[Path] | None = None,
        poll_s: float = 1.0,
        debounce_s: float = 2.0,
    ) -> None:
        self._on_change = on_change
        self._paths = paths if paths is not None else watched_vscdb_paths()
        self._poll_s = poll_s
        self._debounce_s = debounce_s
        self._mtimes: dict[Path, float] = {}
        self._pending: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def paths(self) -> tuple[Path, ...]:
        return tuple(self._paths)

    def start(self) -> None:
        if self._thread is not None or not self._paths:
            return
        for path in self._paths:
            if path.is_file():
                self._mtimes[path] = path.stat().st_mtime
        self._thread = threading.Thread(target=self._loop, daemon=True, name="cairn-vscdb-watch")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _loop(self) -> None:
        while not self._stop.wait(self._poll_s):
            changed = False
            for path in self._paths:
                if not path.is_file():
                    continue
                try:
                    mtime = path.stat().st_mtime
                except OSError:
                    continue
                prev = self._mtimes.get(path)
                if prev is None:
                    self._mtimes[path] = mtime
                elif mtime > prev:
                    self._mtimes[path] = mtime
                    changed = True
            if changed:
                self._pending = time.monotonic()
            if self._pending is not None and time.monotonic() - self._pending >= self._debounce_s:
                self._pending = None
                with contextlib.suppress(Exception):
                    self._on_change()
