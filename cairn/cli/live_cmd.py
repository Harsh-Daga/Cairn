"""cairn live — live capture workspace server and install."""

from __future__ import annotations

import argparse
import threading

from cairn.ingest.live.install import install_live, live_install_status, uninstall_live
from cairn.ingest.live.tail import TailWatcher
from cairn.ingest.project_paths import resolve_git_root
from cairn.live.server import LiveServer


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project

    if args.live_command == "install":
        status = install_live(root, source=args.source)
        print(f"Live install: hooks={', '.join(status.watch_installed) or 'none'}")
        print(f"Tail watchers: {', '.join(status.tail_watchers) or 'none'}")
        print(f"Record: {status.install_record_path}")
        return 0

    if args.live_command == "uninstall":
        if uninstall_live(root):
            print("Live capture uninstalled.")
        else:
            print("No live installation found.")
        return 0

    if args.live_command == "status":
        live_status = live_install_status(root)
        if live_status is None:
            print("Live: not installed")
            return 0
        print("Live: installed")
        print(f"  hooks: {', '.join(live_status.watch_installed) or 'none'}")
        print(f"  tail: {', '.join(live_status.tail_watchers) or 'none'}")
        print(f"  record: {live_status.install_record_path}")
        return 0

    server = LiveServer(root, host=args.host, port=args.port)
    tail_thread: threading.Thread | None = None
    stop_event = threading.Event()
    live_status = live_install_status(root)
    if live_status and live_status.tail_watchers:
        watcher = TailWatcher(root, sources=live_status.tail_watchers)

        def _tail_loop() -> None:
            while not stop_event.is_set():
                watcher.poll_once()
                stop_event.wait(2.0)

        tail_thread = threading.Thread(target=_tail_loop, daemon=True)
        tail_thread.start()
        print(f"Tail watchers active: {', '.join(live_status.tail_watchers)}")

    url = server.base_url
    if args.session:
        print(f"Live workspace: {url}/session/{args.session}")
    else:
        print(f"Live workspace: {url}/")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        stop_event.set()
        if tail_thread is not None:
            tail_thread.join(timeout=3.0)
        server.shutdown()
    return 0
