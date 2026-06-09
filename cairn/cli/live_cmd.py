"""cairn live — live capture workspace server."""

from __future__ import annotations

import argparse

from cairn.ingest.project_paths import resolve_git_root
from cairn.live.server import LiveServer


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    server = LiveServer(root, host=args.host, port=args.port)
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
        server.shutdown()
    return 0
