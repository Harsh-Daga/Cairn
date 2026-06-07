"""`cairn watch` — install capture hooks for Claude Code and Codex (R19.9)."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

WatchSource = Literal["claude-code", "codex"]

CAIRN_WATCH_BEGIN = "# >>> cairn watch >>>"
CAIRN_WATCH_END = "# <<< cairn watch <<<"

_CLAUDE_EVENTS: tuple[tuple[str, str | None], ...] = (
    ("SessionStart", None),
    ("UserPromptSubmit", None),
    ("PreToolUse", "Edit|Write|MultiEdit"),
    ("PostToolUse", "Edit|Write|MultiEdit|Bash"),
    ("Stop", None),
)

_CODEX_EVENTS: tuple[tuple[str, str | None], ...] = (
    ("SessionStart", "startup|resume"),
    ("UserPromptSubmit", None),
    ("PreToolUse", "apply_patch|Edit|Write"),
    ("PostToolUse", "apply_patch|Edit|Write|Bash"),
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


def _install_codex_hooks(target: Path, *, source: WatchSource) -> None:
    existing = target.read_text(encoding="utf-8") if target.is_file() else ""
    if CAIRN_WATCH_BEGIN in existing:
        before, _, after = existing.partition(CAIRN_WATCH_BEGIN)
        _, _, after = after.partition(CAIRN_WATCH_END)
        existing = before + after
    block = f"{CAIRN_WATCH_BEGIN}\n{_build_codex_hooks_toml(source)}\n{CAIRN_WATCH_END}\n"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(existing.rstrip() + "\n\n" + block, encoding="utf-8")


def _codex_config_path(project_root: Path) -> Path:
    project_codex = project_root / ".codex" / "config.toml"
    if project_codex.is_file():
        return project_codex
    return Path.home() / ".codex" / "config.toml"
