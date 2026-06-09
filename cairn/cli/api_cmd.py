"""cairn api — HTTP API server."""

from __future__ import annotations

import argparse

from cairn.api.server import ApiServer
from cairn.ingest.project_paths import resolve_git_root


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    server = ApiServer(root, host=args.host, port=args.port)
    print(f"API: {server.base_url}/v1/openapi.json")
    print(f"Project id: {server.project_id}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        server.shutdown()
    return 0
