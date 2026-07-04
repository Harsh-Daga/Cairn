"""Cairn CLI — the single command surface (Part 17)."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cairn import __version__
from cairn.config import (
    CONFIG_DIR,
    load_config_dict,
    mcp_auto_install_enabled,
    set_setting,
)
from cairn.ingest.detect import detect_sources
from cairn.ingest.ingest import IngestReport, run_ingest
from cairn.ingest.project_paths import parse_since, resolve_git_root
from cairn.ingest.writer import CaptureWriter, SessionSummary
from cairn.ledger.ledger import Ledger

_SOURCE_CHOICES = [
    "claude-code",
    "codex",
    "cursor",
    "hermes",
    "aider",
    "opencode",
    "goose",
    "all",
]

COMMAND_GROUPS: dict[str, tuple[str, ...]] = {
    "Everyday": ("show", "optimize", "dash"),
    "Data": ("sync", "share", "config", "export", "stop"),
    "CI": ("check",),
    "Pillars": ("profile", "behavior", "outcomes", "diagnose", "expect", "mcp"),
}
ALL_COMMANDS: tuple[str, ...] = tuple(c for g in COMMAND_GROUPS.values() for c in g)
HIDDEN_COMMANDS: tuple[str, ...] = ("advanced", "update", "help")


# --- aliases (back-compat redirects) ----------------------------------------


def _security(rest: list[str]) -> list[str]:
    if rest and rest[0] == "encrypt":
        return ["share", "--encrypt", *rest[1:]]
    if rest and rest[0] == "audit":
        return ["check", *rest[1:]]
    return ["check", *rest]


ALIASES: dict[str, Any] = {
    "init": ("check",),
    "validate": ("check",),
    "plan": ("check",),
    "context": ("show",),
    "prompt": ("show",),
    "build": ("optimize",),
    "workflow": ("optimize",),
    "run": ("optimize",),
    "doctor": ("check",),
    "status": ("check",),
    "ingest": ("sync",),
    "watch": ("sync", "--watch"),
    "ls": ("show",),
    "sessions": ("show",),
    "runs": ("show",),
    "report": ("show", "--json"),
    "graph": ("show", "--graph"),
    "artifact": ("show",),
    "diff": ("show", "--diff"),
    "live": ("dash",),
    "render": ("share",),
    "insights": ("optimize",),
    "mine": ("optimize",),
    "replay": ("show", "--graph"),
    "snapshot": ("share",),
    "api": ("dash",),
    "collab": ("share", "--zip"),
    "security": _security,
}


def resolve_alias(old_cmd: str, rest_argv: list[str]) -> list[str]:
    mapping = ALIASES[old_cmd]
    if callable(mapping):
        return list(mapping(list(rest_argv)))
    return [*mapping, *rest_argv]


# --- entry point ------------------------------------------------------------


def _state_dir() -> Path:
    override = os.environ.get("CAIRN_STATE_DIR")
    if override:
        return Path(override)
    return CONFIG_DIR


def _pid_path() -> Path:
    return _state_dir() / "cairn.pid"


def _log_path() -> Path:
    return _state_dir() / "cairn.log"


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if argv and argv[0] == "__daemon__":
        return _run_daemon_child(argv[1:])

    if argv and argv[0] in ALIASES:
        old_cmd = argv[0]
        new_argv = resolve_alias(old_cmd, argv[1:])
        print(
            f"note: 'cairn {old_cmd}' is now 'cairn {' '.join(new_argv[:2])}' — see 'cairn help'",
            file=sys.stderr,
        )
        argv = new_argv

    if not argv:
        return _run_default()

    if argv[0] in ("help", "--help", "-h") and (len(argv) == 1 or argv[0] == "help"):
        return _print_help("-v" in argv or "--verbose" in argv)

    parser = _build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "command", None) is None:
        return _run_default(args)
    return int(args.func(args))


def _print_help(verbose: bool) -> int:
    print("Cairn — local, cross-agent coding analytics that closes the loop.\n")
    print("  cairn            golden path: detect → sync → summary → dashboard")
    print("                   (runs in background by default; use --foreground to attach)")
    print("                   (outside a repo: global mode across all projects)\n")
    for group, commands in COMMAND_GROUPS.items():
        print(f"  {group}")
        print(f"    {' | '.join(commands)}")
        print()
    if verbose:
        print("  Hidden")
        print(f"    {' | '.join(HIDDEN_COMMANDS)}")
        print("    advanced migrate")
        print()
    print("Run `cairn <command> --help` for details, or `cairn help -v` for hidden commands.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cairn", description="Cairn — agent analytics")
    parser.add_argument("--version", action="version", version=f"cairn {__version__}")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser")
    parser.add_argument("--port", type=int, default=8787, help="Dashboard port")
    parser.add_argument(
        "--foreground",
        "-f",
        action="store_true",
        help="Keep the dashboard attached to this terminal (default: background)",
    )
    parser.add_argument("--repo", type=Path, default=None, help="Target repo path")
    parser.add_argument(
        "--global", action="store_true", dest="global_view", help="Global mode across all projects"
    )
    sub = parser.add_subparsers(dest="command")

    _add_show(sub)
    _add_optimize(sub)
    _add_dash(sub)
    _add_sync(sub)
    _add_share(sub)
    _add_stop(sub)
    _add_check(sub)
    _add_hook(sub)
    _add_guard(sub)
    _add_advanced(sub)
    _add_update(sub)
    _add_profile(sub)
    _add_behavior(sub)
    _add_outcomes(sub)
    _add_diagnose(sub)
    _add_expect(sub)
    _add_export(sub)
    _add_fleet(sub)
    _add_mcp(sub)
    _add_config(sub)
    return parser


def _project(args: argparse.Namespace) -> Path:
    repo = getattr(args, "repo", None)
    if repo:
        return Path(str(repo)).resolve()
    project = getattr(args, "project", Path(".")) or Path(".")
    return Path(str(project)).resolve()


def _root(args: argparse.Namespace) -> Path:
    return resolve_git_root(_project(args)) or _project(args)


# --- bare / golden path -----------------------------------------------------


def _run_default(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = argparse.Namespace()
    ns = argparse.Namespace(
        project=getattr(args, "repo", None) or getattr(args, "project", Path(".")) or Path("."),
        source=getattr(args, "source", None),
        since=getattr(args, "since", None),
        port=getattr(args, "port", 8787) or 8787,
        no_open=getattr(args, "no_open", False),
        foreground=getattr(args, "foreground", False),
        global_view=getattr(args, "global_view", False),
    )
    return cmd_default(ns)


def cmd_default(args: argparse.Namespace) -> int:
    project = Path(str(getattr(args, "project", Path(".")) or Path("."))).resolve()
    root = resolve_git_root(project) or project

    print(f"cairn {__version__}\n")
    detected = detect_sources(root)
    if not detected or all(d.sessions_seen == 0 for d in detected):
        _print_empty_state(root)
    else:
        print("Found agent history:")
        active = [d for d in detected if d.sessions_seen > 0]
        total = sum(d.sessions_seen for d in active)
        for d in active:
            loc = f"  ({d.path})" if d.path else ""
            print(f"  {d.source:<14}{d.sessions_seen:>5} sessions{loc}")

        since = parse_since(args.since) if getattr(args, "since", None) else None
        source = getattr(args, "source", None) or "all"
        started = time.monotonic()
        reports = _sync_with_progress(root, source=source, since=since, total=total)
        elapsed = int(time.monotonic() - started)
        _finish_progress(sum(r.inserted + r.skipped for r in reports), total, elapsed)
        print()

        from cairn.ingest.backfill import recompute_rollups

        writer = CaptureWriter(root)
        try:
            recompute_rollups(writer, days=90)
        finally:
            writer.close()

        _print_summary(root)

    if mcp_auto_install_enabled():
        installed = mcp_auto_install_clients(root)
        if installed:
            print(f"MCP config installed for: {', '.join(installed)}")

    port = getattr(args, "port", 8787) or 8787
    no_open = getattr(args, "no_open", False)
    foreground = getattr(args, "foreground", False)
    return start_dashboard(root, port=port, no_open=no_open, foreground=foreground)


def _sync_with_progress(
    root: Path, *, source: str, since: datetime | None, total: int
) -> list[IngestReport]:
    sources = (
        ["claude-code", "codex", "cursor", "hermes", "aider", "opencode", "goose"]
        if source == "all"
        else [source]
    )
    reports: list[IngestReport] = []
    done = 0
    for src in sources:
        batch = run_ingest(root, source=src, since=since)
        if batch:
            reports.extend(batch)
            for r in batch:
                done += r.inserted + r.skipped
                _render_progress(done, total)
    if not reports:
        reports = run_ingest(root, source=source, since=since)
    return reports


def _render_progress(done: int, total: int) -> None:
    total = max(total, 1)
    filled = int(min(1.0, done / total) * 20)
    sys.stderr.write(f"\rSyncing  {'█' * filled}{'░' * (20 - filled)}  {done}/{total}   ")
    sys.stderr.flush()


def _finish_progress(done: int, total: int, elapsed_s: int) -> None:
    total = max(total, done, 1)
    sys.stderr.write(f"\rSyncing  {'█' * 20}  {done}/{total}   {elapsed_s}s\n")
    sys.stderr.flush()


def _print_empty_state(root: Path) -> None:
    print("No agent history found yet.")
    print("  cairn sync --source claude-code --claude-project-dir PATH")
    print("  Opening dashboard for guided setup…")


def _print_summary(root: Path) -> None:
    writer = CaptureWriter(root)
    try:
        sessions = writer.list_sessions(limit=10000)
    finally:
        writer.close()
    if not sessions:
        return
    cost = sum(s.total_cost for s in sessions if s.has_cost)
    tokens = sum(s.total_input_tokens + s.total_output_tokens for s in sessions if s.has_cost)
    waste = sum(s.waste_tokens for s in sessions)
    no_cost = sum(1 for s in sessions if not s.has_cost)
    line = (
        f"{len(sessions)} sessions · ${cost:.2f} spend · {tokens:,} tokens · {waste:,} waste tokens"
    )
    if no_cost:
        line += f" · {no_cost} sessions without token data"
    print(line)


def _read_pid_info() -> dict[str, Any] | None:
    path = _pid_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_pid_info(pid: int, port: int, root: Path) -> None:
    _state_dir().mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": pid,
        "port": port,
        "root": str(root.resolve()),
        "started_at": datetime.now(UTC).isoformat(),
    }
    _pid_path().write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _remove_pid_info() -> None:
    path = _pid_path()
    if path.is_file():
        path.unlink()


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _server_health(port: int, *, timeout_s: float = 1.0) -> bool:
    url = f"http://127.0.0.1:{port}/api/overview"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            return int(resp.status) == 200
    except (
        urllib.error.URLError,
        TimeoutError,
        ValueError,
        http.client.RemoteDisconnected,
        ConnectionResetError,
        OSError,
    ):
        return False


def _running_server(port: int) -> dict[str, Any] | None:
    info = _read_pid_info()
    if info is not None:
        pid = int(info.get("pid") or 0)
        saved_port = int(info.get("port") or 0)
        if saved_port == port and _pid_alive(pid) and _server_health(port):
            return info
        if saved_port == port and not _pid_alive(pid):
            _remove_pid_info()
    if _server_health(port):
        return {"port": port, "pid": None}
    return None


def _spawn_daemon(root: Path, port: int) -> int:
    _state_dir().mkdir(parents=True, exist_ok=True)
    log_path = _log_path()
    with log_path.open("a", encoding="utf-8") as log_f:
        log_f.write(
            f"\n--- cairn daemon start {datetime.now(UTC).isoformat()} "
            f"port={port} root={root.resolve()}\n"
        )
        log_f.flush()
        proc = subprocess.Popen(
            [sys.executable, "-m", "cairn", "__daemon__", str(root.resolve()), str(port)],
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
    _write_pid_info(proc.pid, port, root)
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            msg = f"Background server exited early (code {proc.returncode}). See {_log_path()}"
            raise RuntimeError(msg)
        if _server_health(port, timeout_s=0.5):
            return proc.pid
        time.sleep(0.1)
    proc.terminate()
    _remove_pid_info()
    msg = f"Background server did not become ready on port {port}. See {_log_path()}"
    raise RuntimeError(msg)


def _run_daemon_child(argv: list[str]) -> int:
    if not argv:
        print("usage: cairn __daemon__ ROOT [PORT]", file=sys.stderr)
        return 1
    root = Path(argv[0]).resolve()
    port = int(argv[1]) if len(argv) > 1 else 8787
    from cairn.live.server import LiveServer

    server = LiveServer(root, port=port)
    server.serve_background()

    def _shutdown(*_args: object) -> None:
        server.shutdown()
        _remove_pid_info()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        _remove_pid_info()
    return 0


def cmd_stop(args: argparse.Namespace | None = None) -> int:
    info = _read_pid_info()
    default_port = int(info.get("port") or 8787) if info else 8787
    port = int(getattr(args, "port", None) or default_port) if args is not None else default_port
    listener = _port_listener_pid(port)
    if info is not None:
        pid = int(info.get("pid") or 0)
        if _pid_alive(pid) and listener == pid:
            _kill_port_listener(port)
            print("Dashboard stopped.")
            return 0
        if not _pid_alive(pid):
            _remove_pid_info()
    if listener is not None:
        _kill_port_listener(port)
        print("Dashboard stopped.")
        return 0
    _remove_pid_info()
    print("No background Cairn server running.")
    return 0


def _port_listener_pid(port: int) -> int | None:
    """PID of the process listening on TCP port, if any."""
    try:
        out = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if out.returncode != 0 or not out.stdout.strip():
        return None
    try:
        return int(out.stdout.strip().splitlines()[0])
    except ValueError:
        return None


def _kill_port_listener(port: int) -> bool:
    """Terminate whatever process is listening on port (owned or orphan)."""
    pid = _port_listener_pid(port)
    if pid is None:
        _remove_pid_info()
        return True
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if _port_listener_pid(port) is None:
            _remove_pid_info()
            return True
        time.sleep(0.1)
    survivor = _port_listener_pid(port)
    if survivor is not None:
        try:
            os.kill(survivor, signal.SIGKILL)
        except OSError:
            return False
    _remove_pid_info()
    return _port_listener_pid(port) is None


def _we_own_dashboard(port: int) -> bool:
    """True when our pid file points at the process listening on port."""
    info = _read_pid_info()
    if info is None:
        return False
    if int(info.get("port") or 0) != port:
        return False
    pid = int(info.get("pid") or 0)
    if not _pid_alive(pid):
        return False
    return _port_listener_pid(port) == pid


def _notify_dashboard_refresh(port: int) -> bool:
    """Tell a running dashboard server to broadcast fresh metrics via SSE."""
    url = f"http://127.0.0.1:{port}/api/refresh"
    req = urllib.request.Request(
        url,
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=2.0) as resp:
            return int(resp.status) == 200
    except (urllib.error.URLError, TimeoutError, ValueError):
        return False


def _server_project_root(port: int) -> str | None:
    """Read project_root from a live dashboard (setup scan)."""
    url = f"http://127.0.0.1:{port}/api/setup/scan"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return None
    root = data.get("project_root") if isinstance(data, dict) else None
    return str(root) if root else None


def _stop_dashboard_on_port(port: int) -> bool:
    """Stop the dashboard bound to port, including orphan listeners."""
    if _port_listener_pid(port) is not None:
        return _kill_port_listener(port)
    _remove_pid_info()
    return True


def _needs_dashboard_restart(
    existing: dict[str, Any] | None,
    root: Path,
    port: int,
) -> bool:
    """True when the running server is bound to a different project root."""
    if existing is None:
        return False
    if not _we_own_dashboard(port):
        return True
    current = str(root.resolve())
    saved = existing.get("root")
    if saved and str(Path(str(saved)).resolve()) != current:
        return True
    api_root = _server_project_root(port)
    return bool(api_root and str(Path(api_root).resolve()) != current)


def _open_dashboard(url: str, *, no_open: bool) -> None:
    """Open dashboard in browser with a cache-bust param so stale tabs reload."""
    if no_open:
        return
    webbrowser.open(f"{url.rstrip('/')}/?_={int(time.time())}")


def start_dashboard(
    root: Path,
    *,
    port: int = 8787,
    no_open: bool = False,
    foreground: bool = False,
) -> int:
    url = f"http://127.0.0.1:{port}"
    existing = _running_server(port)
    if existing is not None and _needs_dashboard_restart(existing, root, port):
        if not _we_own_dashboard(port):
            print(f"Replacing foreign dashboard on port {port}…")
        else:
            print("Dashboard project changed — restarting server…")
        if not _stop_dashboard_on_port(port):
            print(f"Could not free port {port}. Try: cairn stop", file=sys.stderr)
            return 1
        existing = None

    if existing is not None:
        pid_note = f" (pid {existing['pid']})" if existing.get("pid") else ""
        print(f"Dashboard already running: {url}{pid_note}")
        _notify_dashboard_refresh(port)
        _open_dashboard(url, no_open=no_open)
        return 0

    if not foreground:
        try:
            pid = _spawn_daemon(root, port)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        print(f"Dashboard: {url}  (background, pid {pid})")
        print(f"Log: {_log_path()}")
        print("Stop with: cairn stop")
        _notify_dashboard_refresh(port)
        _open_dashboard(url, no_open=no_open)
        return 0

    from cairn.live.server import LiveServer

    server = LiveServer(root, port=port)
    server.serve_background()
    print(f"Dashboard: {url}" + ("  (browser not opened)" if no_open else "  (opening browser…)"))
    _notify_dashboard_refresh(port)
    _open_dashboard(url, no_open=no_open)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.shutdown()
        print("\nDashboard stopped.")
    return 0


# --- dash -------------------------------------------------------------------


def _add_dash(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("dash", help="Local dashboard server")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--port", type=int, default=8787)
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--global", action="store_true", dest="global_view")
    p.set_defaults(func=cmd_dash)


def cmd_dash(args: argparse.Namespace) -> int:
    root = _root(args)
    return start_dashboard(
        root,
        port=getattr(args, "port", 8787) or 8787,
        no_open=getattr(args, "no_open", False),
        foreground=True,
    )


# --- stop -------------------------------------------------------------------


def _add_stop(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("stop", help="Stop the background dashboard server")
    p.add_argument("--port", type=int, default=8787, help="Dashboard port to stop")
    p.set_defaults(func=cmd_stop)


# --- sync -------------------------------------------------------------------


def _add_sync(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("sync", help="Ingest from all detected sources")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--source", default="all", choices=_SOURCE_CHOICES)
    p.add_argument("--claude-project-dir", type=Path, default=None)
    p.add_argument("--cursor-workspace", type=Path, default=None)
    p.add_argument("--since", default=None, metavar="DURATION")
    p.add_argument("--watch", action="store_true")
    p.add_argument("--backfill", action="store_true")
    p.add_argument("--verify", action="store_true", help="Report drift between disk and ledger")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_sync)


def cmd_sync(args: argparse.Namespace) -> int:
    root = _root(args)
    since = parse_since(args.since) if getattr(args, "since", None) else None
    source = getattr(args, "source", "all") or "all"
    if getattr(args, "watch", False):
        return _sync_watch(root, source, since)
    if getattr(args, "backfill", False):
        return _sync_backfill(root, getattr(args, "json", False))
    if getattr(args, "verify", False):
        return _sync_verify(root, source, since, getattr(args, "json", False))

    reports = run_ingest(
        root,
        source=source,
        since=since,
        claude_project_dir=getattr(args, "claude_project_dir", None),
        cursor_workspace=getattr(args, "cursor_workspace", None),
    )
    from cairn.ingest.backfill import recompute_rollups

    writer = CaptureWriter(root)
    try:
        recompute_rollups(writer, days=90)
    finally:
        writer.close()

    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "sources": [
                        {"source": r.source, "inserted": r.inserted, "skipped": r.skipped}
                        for r in reports
                    ],
                    "inserted": sum(r.inserted for r in reports),
                    "skipped": sum(r.skipped for r in reports),
                },
                indent=2,
            )
        )
        return 0
    for r in reports:
        print(f"  {r.source}  {r.inserted} added, {r.skipped} skipped")
    inserted = sum(r.inserted for r in reports)
    skipped = sum(r.skipped for r in reports)
    print(f"\nSynced: {inserted} new, {skipped} existing")
    info = _read_pid_info()
    if info is not None:
        port = int(info.get("port") or 8787)
        if _running_server(port) is not None:
            _notify_dashboard_refresh(port)
    return 0


def _sync_backfill(root: Path, as_json: bool) -> int:
    from cairn.ingest.backfill import backfill_ledger

    stats = backfill_ledger(root)
    if as_json:
        print(json.dumps(stats, indent=2))
        return 0
    print(f"Backfilled {stats.get('runs', 0)} runs.")
    return 0


def _sync_verify(
    root: Path,
    source: str,
    since: datetime | None,
    as_json: bool,
) -> int:
    from cairn.ingest.verify import verify_ledger

    reports = verify_ledger(root, source=source, since=since)
    drift = [r for r in reports if r.status != "ok"]
    if as_json:
        print(
            json.dumps(
                {
                    "checked": len(reports),
                    "drift": len(drift),
                    "results": [
                        {
                            "external_id": r.external_id,
                            "source": r.source,
                            "status": r.status,
                            "details": r.details,
                        }
                        for r in reports
                    ],
                },
                indent=2,
            )
        )
        return 1 if drift else 0
    ok = len(reports) - len(drift)
    print(f"Verified {len(reports)} sessions: {ok} ok, {len(drift)} drift/missing")
    for r in drift:
        print(f"  [{r.status}] {r.source}/{r.external_id}: {'; '.join(r.details)}")
    return 1 if drift else 0


def _sync_watch(root: Path, source: str, since: datetime | None) -> int:
    from cairn.ingest.watch import install_watch

    detected = detect_sources(root)
    sources = [d.source for d in detected if d.sessions_seen > 0] if source == "all" else [source]
    for src in sources:
        try:
            install_watch(root, sources=("claude-code" if src == "claude-code" else "codex",))
            print(f"  Installed watch hooks for {src}")
        except Exception as exc:
            print(f"  Warning: could not install hooks for {src}: {exc}")
    for r in run_ingest(root, source=source, since=since):
        print(f"  {r.source}  {r.inserted} added, {r.skipped} skipped")
    print("\nWatching for new sessions... Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(5)
            for r in run_ingest(root, source=source):
                if r.inserted > 0:
                    print(f"  {r.source}  {r.inserted} new sessions")
    except KeyboardInterrupt:
        print("\nStopped watching.")
    return 0


# --- show -------------------------------------------------------------------


def _add_show(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("show", help="List sessions (no id) or show one in detail")
    p.add_argument("session_id", nargs="?", default=None, help="Session/run id, prefix, or 'last'")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--source", default=None)
    p.add_argument("--json", action="store_true")
    p.add_argument("--graph", action="store_true")
    p.add_argument("--diff", metavar="PATH", default=None)
    p.add_argument("--compare", nargs=2, metavar=("A", "B"), default=None)
    p.set_defaults(func=cmd_show)


def cmd_show(args: argparse.Namespace) -> int:
    root = _root(args)
    compare = getattr(args, "compare", None)
    if compare:
        return _show_compare(root, compare[0], compare[1], getattr(args, "json", False))
    sid = getattr(args, "session_id", None) or getattr(args, "id", None)
    if sid is None:
        return _list_sessions(root, args)
    return _show_detail(root, sid, args)


def _list_sessions(root: Path, args: argparse.Namespace) -> int:
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        print("No sessions yet. Run `cairn sync` to ingest agent data.")
        return 0
    writer = CaptureWriter(root)
    try:
        sessions = writer.list_sessions(
            limit=getattr(args, "limit", 20) or 20, source=getattr(args, "source", None)
        )
    finally:
        writer.close()
    if not sessions:
        print("No sessions yet. Run `cairn sync` to ingest agent data.")
        return 0
    if getattr(args, "json", False):
        print(
            json.dumps(
                [
                    {
                        "id": s.external_id,
                        "run_id": s.run_id,
                        "source": s.source,
                        "model": s.model,
                        "started_at": s.started_at,
                        "ended_at": s.ended_at,
                        "status": s.status,
                        "event_count": s.event_count,
                        "input_tokens": s.total_input_tokens,
                        "output_tokens": s.total_output_tokens,
                        "cost": s.total_cost,
                    }
                    for s in sessions
                ],
                indent=2,
            )
        )
        return 0
    print(f"{'ID':<24} {'WHEN':<20} {'SOURCE':<12} {'MODEL':<16} {'EVENTS':>7} {'COST':>10}")
    print("-" * 95)
    for s in sessions:
        when = s.started_at[:16] if s.started_at else ""
        sid = s.external_id[:22] if s.external_id else s.run_id[:8]
        model = (s.model or "-")[:14]
        cost = f"${s.total_cost:.2f}" if s.total_cost is not None else "~"
        print(f"{sid:<24} {when:<20} {s.source:<12} {model:<16} {s.event_count:>7} {cost:>10}")
    return 0


def _resolve_summary(root: Path, token: str) -> SessionSummary | None:
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        return None
    from cairn.ledger.resolve import resolve_id

    ledger = Ledger(db_path)
    try:
        resolved = resolve_id(ledger, token)
    finally:
        ledger.close()
    writer = CaptureWriter(root)
    try:
        if resolved.external_id:
            summary = writer.load_session_by_external_id(resolved.external_id)
            if summary is not None:
                return summary
        for s in writer.list_sessions(limit=10000):
            if s.run_id == resolved.run_id:
                return s
    finally:
        writer.close()
    return None


def _show_detail(root: Path, token: str, args: argparse.Namespace) -> int:
    from cairn.ledger.resolve import AmbiguousIdError, IdNotFoundError

    try:
        summary = _resolve_summary(root, token)
    except AmbiguousIdError as exc:
        print(str(exc))
        return 1
    except IdNotFoundError:
        print(f"Session not found: {token}")
        return 1
    if summary is None:
        print(f"Session not found: {token}")
        return 1
    if getattr(args, "graph", False):
        return _show_graph(root, summary, getattr(args, "json", False))
    if getattr(args, "diff", None):
        return _show_diff(root, summary, args.diff)
    if getattr(args, "json", False):
        return _show_json_report(root, summary)
    return _show_text(root, summary)


def _show_text(root: Path, summary: SessionSummary) -> int:
    writer = CaptureWriter(root)
    try:
        events = writer.load_events(summary.run_id)
    finally:
        writer.close()
    print(f"Session: {summary.external_id}")
    print(f"Source:  {summary.source}")
    print(f"Status:  {summary.status}")
    print(f"Events:  {summary.event_count}")
    print(f"Started: {summary.started_at}")
    if summary.ended_at:
        print(f"Ended:   {summary.ended_at}")
    if summary.cwd:
        print(f"CWD:     {summary.cwd}")
    if summary.git_branch:
        print(f"Branch:  {summary.git_branch}")
    if summary.git_commit:
        print(f"Commit:  {summary.git_commit[:12]}")
    print(f"Tokens:  {summary.total_input_tokens:,} in / {summary.total_output_tokens:,} out")
    if summary.total_cost is not None:
        print(f"Cost:    ${summary.total_cost:.2f}")
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    if tool_calls:
        print(f"\nTool calls ({len(tool_calls)}):")
        for tc in tool_calls[:20]:
            print(f"  {tc.get('seq', '?'):>4}  {tc.get('name', '?')}")
    return 0


def _show_json_report(root: Path, summary: SessionSummary) -> int:
    from cairn.render.session_payload import session_payload

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        payload = session_payload(ledger.connection, run_id=summary.run_id)
    finally:
        ledger.close()
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _show_graph(root: Path, summary: SessionSummary, as_json: bool) -> int:
    from cairn.render.session_payload import session_payload

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        payload = session_payload(ledger.connection, run_id=summary.run_id)
    finally:
        ledger.close()
    graph = payload.get("graph", {})
    if as_json:
        print(json.dumps(graph, indent=2))
    else:
        for node in graph.get("nodes", []):
            print(f"  {node.get('label', node.get('id'))} [{node.get('type')}]")
        for edge in graph.get("edges", []):
            print(f"  {edge.get('source')} -> {edge.get('target')} ({edge.get('kind')})")
    return 0


def _show_diff(root: Path, summary: SessionSummary, path: str) -> int:
    from cairn.render.diff import file_diff_for_session

    print(file_diff_for_session(root, summary.run_id, path))
    return 0


def _show_compare(root: Path, ta: str, tb: str, as_json: bool) -> int:
    from cairn.ledger.resolve import AmbiguousIdError, IdNotFoundError

    try:
        a = _resolve_summary(root, ta)
        b = _resolve_summary(root, tb)
    except (AmbiguousIdError, IdNotFoundError) as exc:
        print(str(exc))
        return 1
    if a is None or b is None:
        print("Both sessions must exist to compare.")
        return 1
    rows = [
        ("session", a.external_id, b.external_id),
        ("source", a.source, b.source),
        ("model", a.model or "-", b.model or "-"),
        ("events", str(a.event_count), str(b.event_count)),
        ("input_tokens", str(a.total_input_tokens), str(b.total_input_tokens)),
        ("output_tokens", str(a.total_output_tokens), str(b.total_output_tokens)),
        (
            "cost",
            f"${a.total_cost:.2f}" if a.total_cost is not None else "~",
            f"${b.total_cost:.2f}" if b.total_cost is not None else "~",
        ),
    ]
    if as_json:
        print(json.dumps({k: {"a": av, "b": bv} for k, av, bv in rows}, indent=2))
        return 0
    print(f"{'METRIC':<16} {'A':<28} {'B':<28}")
    print("-" * 72)
    for k, av, bv in rows:
        print(f"{k:<16} {av:<28} {bv:<28}")
    return 0


# --- optimize ---------------------------------------------------------------


def _add_optimize(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("optimize", help="The loop: evidence → proposals → apply → measure")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--llm", action="store_true")
    p.add_argument("--backend", default=None)
    p.add_argument("--revert", nargs="?", const="all", default=None, metavar="ID")
    p.add_argument("--status", action="store_true")
    p.add_argument("--prune", action="store_true")
    p.add_argument("--targets", action="store_true")
    p.add_argument("--report", action="store_true")
    p.add_argument("--auto", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_optimize)


def cmd_optimize(args: argparse.Namespace) -> int:
    root = _root(args)
    if getattr(args, "targets", False):
        from cairn.optimize.targets import detect_targets

        print(detect_targets(root).describe())
        return 0
    if getattr(args, "report", False):
        return _optimize_report(root, args)
    if getattr(args, "status", False):
        return _optimize_status(root)
    if getattr(args, "prune", False):
        from cairn.optimize.apply import prune_entries

        return int(prune_entries(root))
    if getattr(args, "revert", None) is not None:
        from cairn.optimize.apply import revert_entries

        return int(revert_entries(root, getattr(args, "revert", "all")))
    if getattr(args, "auto", False):
        set_setting("optimize", "auto", True)
        print("Auto mode enabled: cairn will suggest optimizations after sync.")
        return 0
    from cairn.optimize.engine import optimize

    return int(optimize(root, args))


def _optimize_report(root: Path, args: argparse.Namespace) -> int:
    from cairn.insights.engine import weekly_markdown

    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        print("No ledger yet. Run `cairn sync` first.")
        return 0
    ledger = Ledger(db_path)
    try:
        md = weekly_markdown(ledger, days=7)
    finally:
        ledger.close()
    output = getattr(args, "output", None)
    if output:
        Path(output).write_text(md, encoding="utf-8")
        print(f"Wrote weekly report to {output}")
    else:
        print(md)
    return 0


def _optimize_status(root: Path) -> int:
    from cairn.optimize.impact import print_status, run_measurement

    try:
        summary = run_measurement(root)
        pruned = summary.get("pruned", []) or []
        if pruned:
            print(f"Auto-pruned {len(pruned)} regressed rule(s): {', '.join(pruned)}\n")
    except Exception:
        pass
    return int(print_status(root))


# --- share ------------------------------------------------------------------


def _add_share(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("share", help="Produce shareable bundles and receipts")
    p.add_argument("session_id", nargs="?", default=None)
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("-o", "--output", type=Path, default=None)
    p.add_argument("--run", default=None, metavar="RUN_ID")
    p.add_argument("--receipt", action="store_true")
    p.add_argument("--html", action="store_true")
    p.add_argument("--zip", action="store_true")
    p.add_argument("--encrypt", action="store_true")
    p.add_argument("--otlp", action="store_true")
    p.set_defaults(func=cmd_share)


def cmd_share(args: argparse.Namespace) -> int:
    root = _root(args)
    token = getattr(args, "session_id", None)
    if token is None:
        writer = CaptureWriter(root)
        try:
            sessions = writer.list_sessions(limit=1)
        finally:
            writer.close()
        if not sessions:
            print("No sessions found. Run `cairn sync` first.")
            return 1
        token = sessions[0].run_id
    if getattr(args, "receipt", False):
        return _share_receipt(root, token, getattr(args, "output", None))
    if getattr(args, "otlp", False):
        return _share_otlp(root, token, getattr(args, "output", None))
    return _share_html(root, token, getattr(args, "output", None), getattr(args, "zip", False))


def _resolve_run_id(root: Path, token: str) -> str:
    from cairn.ledger.resolve import resolve_id

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        return resolve_id(ledger, token).run_id
    finally:
        ledger.close()


def _share_html(root: Path, token: str, output: Path | None, do_zip: bool) -> int:
    run_id = _resolve_run_id(root, token)
    out = Path(output) if output else root / "outputs" / run_id / "session.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    html = (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>Session {run_id}</title></head><body>"
        f"<p>Session <a href='http://127.0.0.1:8787/session.html?id={run_id}'>"
        f"{run_id}</a> — open with <code>cairn dash</code></p></body></html>"
    )
    out.write_text(html, encoding="utf-8")
    print(f"Wrote {out}")
    if do_zip:
        zp = out.with_suffix(".zip")
        with zipfile.ZipFile(zp, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(out, out.name)
        print(f"Wrote {zp}")
    return 0


def _share_receipt(root: Path, token: str, output: Path | None) -> int:
    from cairn.insights.engine import evaluate
    from cairn.render.session_payload import session_payload

    run_id = _resolve_run_id(root, token)
    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        payload = session_payload(ledger.connection, run_id=run_id)
        insights = evaluate(ledger, days=14)[:3]
    finally:
        ledger.close()
    run = payload["run"]
    lines = [
        f"# Cairn Receipt: {run_id}",
        "",
        f"**Source:** {run.get('source')}",
        f"**Model:** {run.get('model')}",
        f"**Started:** {run.get('started_at')}",
        "",
    ]
    if run.get("has_cost"):
        lines.append(
            f"**Tokens:** {run.get('total_input_tokens', 0):,} in / "
            f"{run.get('total_output_tokens', 0):,} out"
        )
        lines.append(f"**Cost:** ${float(run.get('total_cost') or 0):.4f}")
    else:
        lines.append("**Tokens/Cost:** N/A (source does not expose usage)")
    lines.append(f"**Waste tokens:** {run.get('waste_tokens', 0):,}")
    if insights:
        lines.extend(["", "### Insights", ""])
        for ins in insights:
            lines.append(f"- {ins.title}: {ins.body}")
    text = "\n".join(lines) + "\n"
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"Receipt written to {output}")
    else:
        print(text)
    return 0


def _share_otlp(root: Path, token: str, output: Path | None) -> int:
    run_id = _resolve_run_id(root, token)
    writer = CaptureWriter(root)
    try:
        events = writer.load_events(run_id)
    finally:
        writer.close()
    spans = [
        {
            "name": e.get("type"),
            "attributes": {"tool.name": e.get("tool_name"), "seq": e.get("seq")},
        }
        for e in events
    ]
    text = json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}, indent=2)
    if output:
        Path(output).write_text(text, encoding="utf-8")
        print(f"OTLP export written to {output}")
    else:
        print(text)
    return 0


# --- hook / guard -----------------------------------------------------------


def _add_hook(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("hook", help=argparse.SUPPRESS)
    hp = p.add_subparsers(dest="hook_command", required=True)
    pretool = hp.add_parser("pretooluse", help=argparse.SUPPRESS)
    pretool.add_argument(
        "--mode",
        choices=("advisory", "block"),
        default="advisory",
        help=argparse.SUPPRESS,
    )
    pretool.set_defaults(func=_cmd_hook_pretooluse)
    stop = hp.add_parser("stop", help=argparse.SUPPRESS)
    stop.set_defaults(func=_cmd_hook_stop)


def _cmd_hook_pretooluse(args: argparse.Namespace) -> int:
    from cairn.cli.guard import run_pretooluse_hook

    return run_pretooluse_hook(mode=getattr(args, "mode", "advisory") or "advisory")


def _cmd_hook_stop(_args: argparse.Namespace) -> int:
    from cairn.cli.guard import run_stop_hook

    return run_stop_hook()


def _add_guard(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("guard", help="Install PreToolUse / Stop guard hooks")
    gp = p.add_subparsers(dest="guard_command", required=True)
    install = gp.add_parser("install", help="Install guard hooks for Claude Code and/or Codex")
    install.add_argument("project", nargs="?", default=".", type=Path)
    install.add_argument(
        "--agent",
        choices=("claude", "codex", "both"),
        default="claude",
        help="Target agent (default: claude)",
    )
    install.add_argument(
        "--write",
        action="store_true",
        help="Write merged hooks config (default: print instructions only)",
    )
    install.set_defaults(func=_cmd_guard_install)


def _cmd_guard_install(args: argparse.Namespace) -> int:
    from cairn.cli.guard import guard_install

    return guard_install(
        _root(args),
        agent=getattr(args, "agent", "claude") or "claude",
        write=bool(getattr(args, "write", False)),
    )


# --- check ------------------------------------------------------------------


def _add_check(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("check", help="Preflight checks and budget gates")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--budget-usd", type=float, default=None)
    p.add_argument("--budget-tokens", type=int, default=None)
    p.add_argument("--max-waste-ratio", type=float, default=None)
    p.add_argument(
        "--min-quality",
        type=float,
        default=None,
        dest="min_quality",
        help="Fail if 7d mean quality_score from outcomes is below this",
    )
    p.add_argument("--days", type=int, default=None)
    p.add_argument("--run", default=None, metavar="ID")
    p.add_argument("--json", action="store_true")
    p.add_argument(
        "--format",
        choices=("text", "github"),
        default="text",
        help="Output format (github emits ::error/::warning workflow commands)",
    )
    p.set_defaults(func=cmd_check)


def cmd_check(args: argparse.Namespace) -> int:
    root = _root(args)
    as_json = getattr(args, "json", False)
    fmt = getattr(args, "format", "text") or "text"
    issues: list[dict[str, str]] = [_ledger_summary(root)]
    issues.extend(_check_environment(root))
    issues.extend(_check_plan_window(root))
    if (
        getattr(args, "budget_usd", None)
        or getattr(args, "budget_tokens", None)
        or getattr(args, "max_waste_ratio", None)
    ):
        issues.extend(
            _check_budget_gates(
                root,
                getattr(args, "budget_usd", None),
                getattr(args, "budget_tokens", None),
                getattr(args, "max_waste_ratio", None),
                getattr(args, "days", None),
                getattr(args, "run", None),
            )
        )
    min_quality = getattr(args, "min_quality", None)
    if min_quality is not None:
        issues.extend(_check_quality_gate(root, float(min_quality)))
    exit_code = 1 if any(i.get("severity") == "error" for i in issues) else 0
    if as_json:
        print(json.dumps(issues, indent=2))
    elif fmt == "github":
        for issue in issues:
            sev = issue.get("severity", "info")
            if sev not in ("error", "warning"):
                continue
            gate = issue.get("gate") or "check"
            msg = issue.get("message", "")
            line = f"::{sev} title=cairn check::{gate}: {msg}"
            print(line)
    else:
        for issue in issues:
            prefix = {"error": "ERROR", "warning": "WARN", "info": "OK"}.get(
                issue.get("severity", "info"), "info"
            )
            print(f"  [{prefix}] {issue.get('message', '')}")
    return exit_code


def _ledger_summary(root: Path) -> dict[str, str]:
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        return {"severity": "info", "message": "Ledger: none yet (run `cairn sync`)"}
    writer = CaptureWriter(root)
    try:
        sessions = writer.list_sessions(limit=10000)
    finally:
        writer.close()
    n = len(sessions)
    last_sync = max((s.started_at for s in sessions if s.started_at), default=None)
    last = last_sync[:16] if last_sync else "never"
    return {"severity": "info", "message": f"Ledger: {n} sessions, last activity {last}"}


def _check_environment(root: Path) -> list[dict[str, str]]:
    db_path = root / ".cairn" / "ledger.db"
    if db_path.is_file():
        return [{"severity": "info", "message": f"Ledger found at {db_path}"}]
    return [
        {
            "severity": "warning",
            "gate": "environment",
            "message": "No ledger found. Run `cairn sync` first.",
        }
    ]


def _check_plan_window(root: Path) -> list[dict[str, str]]:
    from cairn.context.gauge import compute_gauge

    gauge = compute_gauge(root)
    if gauge.limit is None:
        return []
    by_src = ", ".join(f"{k}: {v:,}" for k, v in gauge.by_source.items())
    detail = f"({by_src})" if by_src else ""
    if gauge.exceeded:
        return [
            {
                "severity": "error",
                "gate": "plan-window",
                "message": (
                    f"5h window exceeded: {gauge.total_tokens:,} > {gauge.limit:,} "
                    f"tokens {detail}"
                ).strip(),
            }
        ]
    return [
        {
            "severity": "info",
            "message": (
                f"5h window OK: {gauge.total_tokens:,} / {gauge.limit:,} tokens {detail}"
            ).strip(),
        }
    ]


def _check_budget_gates(
    root: Path,
    budget_usd: float | None,
    budget_tokens: int | None,
    max_waste: float | None,
    days: int | None,
    run_id: str | None,
) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    writer = CaptureWriter(root)
    try:
        sessions = writer.list_sessions(limit=1000)
    finally:
        writer.close()
    total_cost = sum(s.total_cost or 0 for s in sessions)
    total_tokens = sum(s.total_input_tokens + s.total_output_tokens for s in sessions)
    if budget_usd is not None:
        if total_cost > budget_usd:
            issues.append(
                {
                    "severity": "error",
                    "gate": "budget-usd",
                    "message": f"Budget exceeded: ${total_cost:.2f} > ${budget_usd:.2f}",
                }
            )
        else:
            issues.append(
                {"severity": "info", "message": f"Budget OK: ${total_cost:.2f} / ${budget_usd:.2f}"}
            )
    if budget_tokens is not None:
        if total_tokens > budget_tokens:
            issues.append(
                {
                    "severity": "error",
                    "gate": "budget-tokens",
                    "message": f"Token budget exceeded: {total_tokens:,} > {budget_tokens:,}",
                }
            )
        else:
            issues.append(
                {
                    "severity": "info",
                    "message": f"Token budget OK: {total_tokens:,} / {budget_tokens:,}",
                }
            )
    if max_waste is not None:
        db_path = root / ".cairn" / "ledger.db"
        if db_path.is_file():
            ledger = Ledger(db_path)
            try:
                waste_ratio = _compute_waste_ratio(ledger, days=days or 7)
            finally:
                ledger.close()
            if waste_ratio > max_waste:
                issues.append(
                    {
                        "severity": "error",
                        "gate": "max-waste-ratio",
                        "message": f"Waste ratio exceeded: {waste_ratio:.1%} > {max_waste:.1%}",
                    }
                )
            else:
                issues.append(
                    {
                        "severity": "info",
                        "message": f"Waste ratio OK: {waste_ratio:.1%} / {max_waste:.1%}",
                    }
                )
        else:
            issues.append(
                {
                    "severity": "warning",
                    "message": "No ledger for waste ratio check; run `cairn sync` first.",
                }
            )
    return issues


def _compute_waste_ratio(ledger: Ledger, *, days: int) -> float:
    row = ledger.connection.execute(
        "SELECT SUM(waste_tokens) AS waste, "
        "SUM(total_input_tokens + cache_creation_tokens) AS inp, "
        "SUM(tool_call_count) AS tool_calls FROM runs "
        "WHERE date(started_at) >= date('now', ?)",
        (f"-{days} days",),
    ).fetchone()
    if row is not None:
        waste = int(row["waste"] or 0)
        inp = int(row["inp"] or 0)
        if inp > 0 and waste > 0:
            return waste / inp
        tool_calls = int(row["tool_calls"] or 0)
        if tool_calls > 0:
            waste_events = ledger.connection.execute(
                "SELECT COUNT(*) FROM events e JOIN runs r ON r.run_id = e.run_id "
                "WHERE e.waste_category IS NOT NULL AND date(r.started_at) >= date('now', ?)",
                (f"-{days} days",),
            ).fetchone()[0]
            return int(waste_events) / tool_calls
    return 0.0


def _mean_quality_score_7d(root: Path) -> float | None:
    db_path = root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        return None
    ledger = Ledger(db_path)
    try:
        row = ledger.connection.execute(
            """
            SELECT AVG(o.quality_score) AS m
            FROM outcomes o JOIN runs r ON o.run_id = r.run_id
            WHERE r.started_at >= date('now', '-7 days')
              AND o.quality_score IS NOT NULL
            """
        ).fetchone()
    finally:
        ledger.close()
    if row is None or row["m"] is None:
        return None
    return float(row["m"])


def _check_quality_gate(root: Path, min_quality: float) -> list[dict[str, str]]:
    mean = _mean_quality_score_7d(root)
    if mean is None:
        return [
            {
                "severity": "warning",
                "gate": "min-quality",
                "message": (
                    "No quality scores in the last 7 days; run `cairn sync` "
                    "and capture outcomes first."
                ),
            }
        ]
    if mean < min_quality:
        return [
            {
                "severity": "error",
                "gate": "min-quality",
                "message": f"Quality gate failed: 7d mean {mean:.1f} < {min_quality:.1f}",
            }
        ]
    return [
        {"severity": "info", "message": f"Quality gate OK: 7d mean {mean:.1f} >= {min_quality:.1f}"}
    ]


# --- profile / behavior / outcomes -----------------------------------------


def _add_profile(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("profile", help="Context regions + findings + recoverable $ for a run")
    p.add_argument("session_id", nargs="?", default="last")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_profile)


def cmd_profile(args: argparse.Namespace) -> int:
    root = _root(args)
    if not (root / ".cairn" / "ledger.db").is_file():
        print("No sessions yet. Run `cairn sync` to ingest agent data.")
        return 0
    token = getattr(args, "session_id", None) or "last"
    run_id = _resolve_run_id_or_none(root, token)
    if run_id is None:
        print(f"Session not found: {token}")
        return 1
    writer = CaptureWriter(root)
    try:
        from cairn.profile.compute import profile_run

        payload = profile_run(writer, run_id)
    finally:
        writer.close()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    _print_profile(payload)
    return 0


def _resolve_run_id_or_none(root: Path, token: str) -> str | None:
    from cairn.ledger.resolve import AmbiguousIdError, IdNotFoundError, resolve_id

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        try:
            return resolve_id(ledger, token).run_id
        except (AmbiguousIdError, IdNotFoundError):
            return None
    finally:
        ledger.close()


def _print_profile(payload: dict[str, Any]) -> None:
    print(f"Run:      {payload.get('run_id')}")
    if payload.get("model"):
        print(f"Model:    {payload['model']}")
    if payload.get("turn_count"):
        print(f"Turns:    {payload['turn_count']}")
    regions = payload.get("regions") or []
    if regions:
        print(f"\nContext regions ({len(regions)}):")
        print(f"  {'REGION':<20} {'TOKENS':>8} {'COST':>10} {'TURNS':>10} HASH")
        print("  " + "-" * 70)
        for r in regions:
            turns = f"{r.get('first_turn')}->{r.get('last_seen_turn')}"
            cost = f"${r.get('cost', 0):.4f}" if r.get("cost") else "-"
            h = (r.get("content_hash") or "-")[:12]
            print(f"  {r.get('region', ''):<20} {r.get('tokens', 0):>8} {cost:>10} {turns:>10} {h}")
    else:
        print("\nNo context regions.")
    findings = payload.get("findings") or []
    if findings:
        print(f"\nFindings ({len(findings)}):")
        for f in findings:
            cost = f" ${f.get('cost_usd', 0):.4f}" if f.get("cost_usd") else ""
            sev = f.get("severity", "").upper()
            print(
                f"  [{sev:<6}] {f.get('type')}: {f.get('tokens', 0)} tokens{cost}"
            )
            print(f"         fix: {f.get('fix')}")
    reb = payload.get("rebilling") or {}
    if reb:
        print("\nRe-billing (recoverable):")
        print(f"  tokens: {reb.get('tokens', 0)}")
        reb_cost = reb.get("cost_usd")
        print(f"  cost:   ${reb_cost:.4f}" if reb_cost else "  cost:   -")
    for n in payload.get("data_notes") or []:
        print(f"  - {n}")


def _add_behavior(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("behavior", help="Behavioral fingerprint + AMDM drift")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--project-name", default=None)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_behavior)


def cmd_behavior(args: argparse.Namespace) -> int:
    root = _root(args)
    if not (root / ".cairn" / "ledger.db").is_file():
        print("No sessions yet. Run `cairn sync` to ingest agent data.")
        return 0
    from cairn.metrics.fingerprint import behavior_payload

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        payload = behavior_payload(
            ledger.connection,
            days=getattr(args, "days", 30) or 30,
            project=getattr(args, "project_name", None),
        )
    finally:
        ledger.close()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    _print_behavior(payload)
    return 0


def _print_behavior(payload: dict[str, Any]) -> None:
    fps = payload.get("fingerprints") or []
    if not fps:
        print("No fingerprints in range.")
        for n in payload.get("data_notes", []):
            print(f"  - {n}")
        return
    print(f"Fingerprints ({len(fps)}):")
    header = (
        f"  {'RUN':<22} {'PROJECT':<16} {'MODEL':<16} "
        f"{'R/W':>6} {'EXP':>6} {'RETRY':>6} {'TURNS':>6}"
    )
    print(header)
    print("  " + "-" * 80)
    for f in fps:
        print(
            f"  {(f.get('run_id', '')[:20]):<22} {(f.get('project') or '-')[:14]:<16} "
            f"{(f.get('model') or '-')[:14]:<16} {f.get('read_write_ratio', 0):>6.2f} "
            f"{f.get('exploration_ratio', 0):>6.2f} {f.get('retry_rate', 0):>6.2f} "
            f"{f.get('turn_count', 0):>6}"
        )
    drift = payload.get("drift") or []
    if drift:
        print(f"\nDRIFT signals ({len(drift)}):")
        for d in drift:
            print(
                f"  [{d.get('kind')}] run {d.get('run_id', '')[:20]}: "
                f"D²={d.get('d_squared')} > χ²({d.get('d_eff')})={d.get('threshold')} "
                f"(distance={d.get('distance')})"
            )
    else:
        print("\nNo joint-shock drift detected.")
    gradual = payload.get("gradual") or []
    if gradual:
        print(f"\nDRIFT_GRADUAL ({len(gradual)}):")
        for g in gradual:
            print(f"  project={g.get('project')} model={g.get('model')} axes={g.get('axes')}")
    radar = payload.get("radar")
    if radar:
        print(f"\nRadar ({radar.get('project')}/{radar.get('model')}):")
        labels = radar.get("labels", [])
        cur = radar.get("current_week", [])
        base = radar.get("baseline", [])
        for i, lab in enumerate(labels):
            c = cur[i] if i < len(cur) else 0
            b = base[i] if i < len(base) else 0
            print(f"  {lab:<14} cur={c:.3f} base={b:.3f}")
    for n in payload.get("data_notes", []):
        print(f"  note: {n}")


def _add_outcomes(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("outcomes", help="Agent Quality Score + cost-per-success")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_outcomes)


def cmd_outcomes(args: argparse.Namespace) -> int:
    root = _root(args)
    if not (root / ".cairn" / "ledger.db").is_file():
        print("No sessions yet. Run `cairn sync` to ingest agent data.")
        return 0
    from cairn.outcomes import outcomes_payload

    ledger = Ledger(root / ".cairn" / "ledger.db")
    try:
        payload = outcomes_payload(ledger.connection, days=getattr(args, "days", 30) or 30)
    finally:
        ledger.close()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    _print_outcomes(payload)
    return 0


def _print_outcomes(payload: dict[str, Any]) -> None:
    q = payload.get("quality")
    if q is None:
        print("No outcomes in range.")
        for n in payload.get("data_notes", []):
            print(f"  - {n}")
        return
    mean = q.get("mean")
    print("Agent Quality Score:")
    print(f"  mean: {mean if mean is not None else '-'}")
    print(f"  tiers: {q.get('tier_counts')}")
    cps = payload.get("cost_per_success") or {}
    print("\nCost per success (non-Lucky only):")
    cps_v = cps.get("cost_per_success")
    print(f"  cost_per_success: {cps_v if cps_v is not None else '- (div0 guard)'}")
    print(f"  non_lucky_successes: {cps.get('non_lucky_successes', 0)}")
    print(f"  total_cost: {cps.get('total_cost', 0.0)}")
    if cps.get("variance") is not None:
        print(f"  variance: {cps['variance']}")
    funnel = payload.get("funnel") or {}
    if funnel:
        print("\nFunnel:")
        print(
            f"  sessions -> commits -> passing tests: {funnel.get('sessions')} -> "
            f"{funnel.get('commits_landed')} -> {funnel.get('passing_tests')}"
        )
    sessions = payload.get("sessions") or []
    if sessions:
        print(f"\nSessions ({len(sessions)}):")
        print(f"  {'RUN':<22} {'TIER':<8} {'Q':>6} {'COMMIT':>7} {'LUCKY':>6} {'CPS':>10}")
        print("  " + "-" * 64)
        for s in sessions:
            c = s.get("cost_per_success")
            cps_s = f"${c:.4f}" if c is not None else "-"
            print(
                f"  {s.get('run_id', '')[:20]:<22} {s.get('tier') or '-':<8} "
                f"{s.get('quality_score') or 0:>6.1f} "
                f"{'yes' if s.get('commit_landed') else 'no':>7} "
                f"{'yes' if s.get('lucky_pass') else 'no':>6} {cps_s:>10}"
            )
    for n in payload.get("data_notes", []):
        print(f"  note: {n}")


# --- diagnose / expect / export / fleet -----------------------------------


def _add_diagnose(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("diagnose", help="Session autopsy in the terminal")
    p.add_argument("session_id", nargs="?", default="last")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_diagnose)


def cmd_diagnose(args: argparse.Namespace) -> int:
    root = _root(args)
    db = root / ".cairn" / "ledger.db"
    if not db.is_file():
        print("No ledger. Run `cairn sync` first.")
        return 1
    from cairn.render.session_payload import session_payload

    ledger = Ledger(db)
    try:
        sid = getattr(args, "session_id", "last") or "last"
        if sid == "last":
            row = ledger.connection.execute(
                "SELECT run_id FROM runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
            if row is None:
                print("No sessions.")
                return 1
            run_id = str(row["run_id"])
        else:
            row = ledger.connection.execute(
                "SELECT run_id FROM runs WHERE run_id = ? OR external_id = ?",
                (sid, sid),
            ).fetchone()
            if row is None:
                print(f"Session not found: {sid}")
                return 1
            run_id = str(row["run_id"])
        payload = session_payload(ledger.connection, run_id=run_id)
    finally:
        ledger.close()
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
        return 0
    print(payload.get("narrative") or "No narrative available.")
    diag = payload.get("diagnostics") or {}
    if diag:
        print(f"\nOutcome: {diag.get('outcome_label')} ({diag.get('label_source')})")
        print(f"Category: {diag.get('primary_category')} / {diag.get('secondary_category')}")
        if diag.get("failure_origin_event_id"):
            print(f"Failure origin: event {diag['failure_origin_event_id']}")
    norm = payload.get("normalized") or {}
    if norm.get("label"):
        print(f"Expected vs actual: {norm['label']}")
    rewind = payload.get("rewind_suggestion")
    if rewind:
        print("\nRewind suggestion (human approval required):")
        print(f"  {rewind.get('command')}")
        print(f"  {rewind.get('note')}")
    return 0


def _add_expect(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("expect", help="Difficulty-aware budget forecast for a task")
    p.add_argument("prompt")
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_expect)


def cmd_expect(args: argparse.Namespace) -> int:
    from cairn.mcp.tools import _expected_cost, open_context

    ctx = open_context(_root(args))
    try:
        result = _expected_cost(ctx, {"task": args.prompt})
    finally:
        ctx.close()
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
        return 0
    bucket = result.get("difficulty_bucket", "standard")
    exp = result.get("expected_tokens")
    if exp is not None:
        print(f"Bucket: {bucket} — expected ~{int(exp):,} tokens")
    else:
        print(f"Bucket: {bucket} — insufficient baseline ({result.get('data_notes')})")
    return 0


def _add_export(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("export", help="Export scrubbed ledger bundle")
    p.add_argument("-o", "--output", required=True, type=Path)
    p.add_argument("project", nargs="?", default=".", type=Path)
    p.add_argument("--since", default=None)
    p.add_argument("--with-snippets", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_export)


def cmd_export(args: argparse.Namespace) -> int:
    from cairn.fleet.export import export_bundle

    result = export_bundle(
        _root(args),
        Path(args.output),
        since=getattr(args, "since", None),
        with_snippets=bool(getattr(args, "with_snippets", False)),
    )
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2))
        return 0 if "error" not in result else 1
    if "error" in result:
        print(result["error"])
        return 1
    print(f"Exported to {result['path']}")
    print("Manifest:")
    for line in result.get("manifest", []):
        print(f"  {line}")
    return 0


def _add_fleet(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("fleet", help="Team fleet merge/serve")
    fp = p.add_subparsers(dest="fleet_command", required=True)
    mp = fp.add_parser("merge", help="Merge bundles into fleet.db")
    mp.add_argument("bundles", nargs="+", type=Path)
    mp.add_argument("-o", "--output", required=True, type=Path)
    mp.set_defaults(func=cmd_fleet_merge)
    sp = fp.add_parser("serve", help="Serve team dashboard (alias: cairn dash)")
    sp.add_argument("project", nargs="?", default=".", type=Path)
    sp.add_argument("--port", type=int, default=8788)
    sp.set_defaults(func=cmd_fleet_serve)


def cmd_fleet_merge(args: argparse.Namespace) -> int:
    from cairn.fleet.export import merge_bundles

    result = merge_bundles([Path(b) for b in args.bundles], Path(args.output))
    print(f"Merged {result['runs_merged']} runs -> {result['output']}")
    return 0


def cmd_fleet_serve(args: argparse.Namespace) -> int:
    args.port = getattr(args, "port", 8788) or 8788
    return cmd_dash(args)


# --- mcp --------------------------------------------------------------------


def _add_mcp(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("mcp", help="MCP server (install config / run stdio server)")
    mp = p.add_subparsers(dest="mcp_command")
    mp.add_parser("install", help="Print the MCP client config block")
    mp.add_parser("serve", help="Run the stdio MCP server")
    p.set_defaults(func=cmd_mcp)


def cmd_mcp(args: argparse.Namespace) -> int:
    cmd = getattr(args, "mcp_command", None)
    if cmd == "install":
        return _mcp_install(args)
    if cmd == "serve":
        from cairn.mcp.server import serve

        return serve(_root(args))
    print("usage: cairn mcp <install|serve>")
    return 1


def _mcp_install(args: argparse.Namespace) -> int:
    root = _root(args)
    client = _detect_mcp_client()
    exe = sys.executable or "python3"
    print(f"# Detected MCP client: {client}")
    print(f"# Paste this into {_mcp_config_path(client)}:\n")
    print(_mcp_config_block(client, exe, root))
    return 0


def _detect_mcp_clients() -> list[str]:
    home = Path.home()
    clients: list[str] = []
    if (home / ".claude.json").is_file() or (home / ".claude").is_dir():
        clients.append("claude")
    if (home / ".cursor").is_dir():
        clients.append("cursor")
    if (home / ".codex").is_dir():
        clients.append("codex")
    return clients


def _detect_mcp_client() -> str:
    clients = _detect_mcp_clients()
    return clients[0] if clients else "claude"


def _mcp_config_path(client: str) -> str:
    if client == "cursor":
        return "~/.cursor/mcp.json"
    if client == "codex":
        return "~/.codex/config.toml"
    return "~/.claude.json"


def _mcp_config_block(client: str, exe: str, root: Path) -> str:
    root_str = str(root)
    if client == "codex":
        return (
            f'[mcp_servers.cairn]\ncommand = "{exe}"\n'
            f'args = ["-m", "cairn", "mcp", "serve"]\ncwd = "{root_str}"\n'
        )
    return (
        "{\n"
        f'  "mcpServers": {{\n'
        f'    "cairn": {{\n'
        f'      "command": "{exe}",\n'
        f'      "args": ["-m", "cairn", "mcp", "serve"],\n'
        f'      "cwd": "{root_str}"\n'
        f"    }}\n"
        f"  }}\n"
        f"}}"
    )


def _mcp_already_installed(client: str) -> bool:
    path = Path(_mcp_config_path(client)).expanduser()
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    if client == "codex":
        return "[mcp_servers.cairn]" in text
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return '"cairn"' in text and "mcpServers" in text
    servers = data.get("mcpServers") if isinstance(data, dict) else None
    return isinstance(servers, dict) and "cairn" in servers


def _mcp_write_config(client: str, exe: str, root: Path) -> bool:
    """Merge Cairn into the client MCP config. Returns True if newly written."""
    if _mcp_already_installed(client):
        return False
    path = Path(_mcp_config_path(client)).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    if client == "codex":
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
        block = _mcp_config_block(client, exe, root)
        merged = existing.rstrip() + ("\n\n" if existing.strip() else "") + block
        path.write_text(merged if merged.endswith("\n") else merged + "\n", encoding="utf-8")
        return True
    data: dict[str, Any] = {}
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except json.JSONDecodeError:
            data = {}
    servers = data.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        servers = {}
        data["mcpServers"] = servers
    servers["cairn"] = {
        "command": exe,
        "args": ["-m", "cairn", "mcp", "serve"],
        "cwd": str(root.resolve()),
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return True


def mcp_auto_install_clients(root: Path) -> list[str]:
    """Auto-write MCP config for each detected client (default-on)."""
    if not mcp_auto_install_enabled():
        return []
    exe = sys.executable or "python3"
    installed: list[str] = []
    for client in _detect_mcp_clients():
        if _mcp_write_config(client, exe, root):
            installed.append(client)
    return installed


# --- config -----------------------------------------------------------------


def _add_config(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("config", help="Read/write ~/.config/cairn/config.toml")
    cp = p.add_subparsers(dest="config_command")
    g = cp.add_parser("get", help="Print config (or one value: section.key)")
    g.add_argument("key", nargs="?", default=None)
    s = cp.add_parser("set", help="Set a value: config set section.key value")
    s.add_argument("key")
    s.add_argument("value")
    p.set_defaults(func=cmd_config)


def cmd_config(args: argparse.Namespace) -> int:
    cmd = getattr(args, "config_command", None)
    if cmd == "set":
        return _config_set(args.key, args.value)
    return _config_get(getattr(args, "key", None))


def _config_get(key: str | None) -> int:
    from cairn.config import DIAGNOSE_DEFAULTS

    data = load_config_dict()
    if key is None:
        print(json.dumps(data, indent=2, default=str))
        return 0
    if key == "diagnose":
        merged = {**DIAGNOSE_DEFAULTS, **data.get("diagnose", {})}
        print(json.dumps(merged, indent=2, default=str))
        return 0
    if "." not in key:
        print(json.dumps(data.get(key, {}), indent=2, default=str))
        return 0
    section, _, k = key.partition(".")
    val = data.get(section, {}).get(k)
    print("" if val is None else json.dumps(val, default=str))
    return 0


def _config_set(key: str, value: str) -> int:
    if "." not in key:
        print("Error: key must be section.key", file=sys.stderr)
        return 1
    section, _, k = key.partition(".")
    coerced = _coerce_value(value)
    try:
        set_setting(section, k, coerced)
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Set {section}.{k} = {coerced!r}")
    return 0


def _coerce_value(value: str) -> Any:
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    if low in ("null", "none"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


# --- advanced (migrate only) ------------------------------------------------


def _add_advanced(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("advanced", help=argparse.SUPPRESS)
    adv = p.add_subparsers(dest="advanced_command")
    adv.add_parser("migrate", help="Drop + re-ingest the ledger (schema mismatch recovery)")
    adv.add_parser("tokenizer-check", help="Report tokenizer calibration error vs fixtures")
    post = adv.add_parser("post-session", help=argparse.SUPPRESS)
    post.add_argument("--session", default="")
    post.add_argument("--cwd", default="")
    post.set_defaults(func=_cmd_advanced_post_session)
    p.set_defaults(func=cmd_advanced)


def _cmd_advanced_post_session(args: argparse.Namespace) -> int:
    from cairn.cli.guard import run_post_session

    return run_post_session(
        session_id=getattr(args, "session", "") or "",
        cwd=getattr(args, "cwd", "") or "",
    )


def cmd_advanced(args: argparse.Namespace) -> int:
    sub = getattr(args, "advanced_command", None)
    if sub == "migrate":
        return _advanced_migrate(args)
    if sub == "tokenizer-check":
        return _advanced_tokenizer_check(args)
    if sub == "post-session":
        return _cmd_advanced_post_session(args)
    print("Unknown advanced command. Use: migrate | tokenizer-check | post-session")
    return 1


def _advanced_tokenizer_check(args: argparse.Namespace) -> int:
    from cairn.ingest.tokenizer_audit import run_tokenizer_check

    report = run_tokenizer_check()
    print(json.dumps(report, indent=2))
    if report.get("error"):
        return 1
    return 0


def _advanced_migrate(args: argparse.Namespace) -> int:
    root = _root(args)
    db = root / ".cairn" / "ledger.db"
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(db) + suffix)
        if p.is_file():
            p.unlink()
    print(f"Dropped ledger at {db}")
    from cairn.ingest.backfill import backfill_ledger

    stats = backfill_ledger(root)
    print(f"Re-ingested {stats.get('runs', 0)} runs.")
    return 0


# --- update -----------------------------------------------------------------


def _add_update(sub: argparse._SubParsersAction[Any]) -> None:
    p = sub.add_parser("update", help="Upgrade cairn-workspace (hidden)")
    p.set_defaults(func=cmd_update)


def cmd_update(_args: argparse.Namespace) -> int:
    if shutil.which("uv"):
        print("Upgrading via uv tool…")
        proc = subprocess.run(["uv", "tool", "upgrade", "cairn-workspace"], check=False)
        if proc.returncode == 0:
            print("Done. Run `cairn --version` to confirm.")
            return 0
        print("uv upgrade failed; try: uv tool install --upgrade cairn-workspace")
        return proc.returncode
    if shutil.which("pipx"):
        print("Upgrading via pipx…")
        return subprocess.run(["pipx", "upgrade", "cairn-workspace"], check=False).returncode
    print("Upgrade manually:\n  uv tool install --upgrade cairn-workspace")
    print("  # or: pipx upgrade cairn-workspace")
    print("  # or: pip install --upgrade cairn-workspace")
    return 0


if __name__ == "__main__":
    sys.exit(main())
