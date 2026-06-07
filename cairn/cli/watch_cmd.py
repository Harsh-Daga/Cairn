"""cairn watch — install/uninstall/status capture hooks (R19.9)."""

from __future__ import annotations

import argparse

from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.watch import WatchSource, install_watch, uninstall_watch, watch_status


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project

    if args.watch_command == "install":
        sources = _sources(args.source)
        status = install_watch(root, sources=sources)
        print(f"Installed watch hooks for: {', '.join(status.installed)}")
        print(f"Record: {status.install_record_path}")
        if status.hook_invocation:
            print(f"Hook command: {status.hook_invocation} hook --event … --source …")
        if "codex" in status.installed:
            print(
                "Codex: trust hooks once via /hooks in the TUI, then restart Codex "
                "so SessionStart runs with hooks enabled."
            )
            print(
                "Automation: --dangerously-bypass-hook-trust skips the trust prompt."
            )
        return 0

    if args.watch_command == "uninstall":
        if uninstall_watch(root):
            print("Watch hooks uninstalled; backups restored.")
        else:
            print("No watch installation found.")
        return 0

    current = watch_status(root)
    if current is None:
        print("Watch: not installed")
        return 0
    print(f"Watch: installed ({', '.join(current.installed)})")
    print(f"Record: {current.install_record_path}")
    if current.hook_invocation:
        print(f"Hook command: {current.hook_invocation} hook --event … --source …")
    for name, path in current.backups.items():
        print(f"  backup {name}: {path}")
    return 0


def _sources(raw: str | None) -> tuple[WatchSource, ...]:
    if raw is None or raw == "all":
        return ("claude-code", "codex")
    if raw == "claude-code":
        return ("claude-code",)
    if raw == "codex":
        return ("codex",)
    msg = f"unsupported watch source: {raw!r}"
    raise ValueError(msg)
