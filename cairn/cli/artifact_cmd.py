"""cairn artifact — artifact inventory and lineage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cairn.artifacts.registry import ArtifactRegistry
from cairn.ingest.project_paths import resolve_git_root
from cairn.ingest.writer import CaptureWriter


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    registry = ArtifactRegistry(root)
    try:
        if args.artifact_command == "list":
            run_id = _resolve_run_id(root, getattr(args, "session_id", None))
            if run_id is None:
                print("No artifacts found.")
                return 0
            artifacts = registry.list_for_run(run_id)
            if not artifacts:
                print("No artifacts for this run.")
                return 0
            if args.json:
                print(json.dumps([a.to_dict() for a in artifacts], indent=2))
                return 0
            print(f"{'HASH':<14} {'KIND':<10}  PATH")
            print("-" * 72)
            for art in artifacts:
                path = art.path_rel or "-"
                print(f"{art.content_hash[:14]:<14} {art.kind:<10}  {path}")
            return 0

        if args.artifact_command == "show":
            selected = registry.get(args.hash)
            if selected is None:
                print(f"Artifact not found: {args.hash}")
                return 1
            if args.json:
                print(json.dumps(selected.to_dict(), indent=2))
            else:
                print(f"hash:  {selected.content_hash}")
                print(f"kind:  {selected.kind}")
                print(f"path:  {selected.path_rel or '-'}")
                print(f"run:   {selected.run_id or '-'}")
            return 0

        if args.artifact_command == "lineage":
            selected = registry.get(args.hash)
            if selected is None:
                print(f"Artifact not found: {args.hash}")
                return 1
            edges = registry.lineage(args.hash)
            if args.json:
                print(
                    json.dumps(
                        {
                            "artifact": selected.to_dict(),
                            "edges": [e.__dict__ for e in edges],
                        },
                        indent=2,
                    )
                )
                return 0
            if not edges:
                print("No lineage edges recorded.")
                return 0
            for edge in edges:
                print(f"{edge.relation}: {edge.from_id[:12]} → {edge.to_id[:12]}")
            return 0
    finally:
        registry.close()
    return 1


def _resolve_run_id(root: Path, session_id: str | None) -> str | None:
    if session_id is None:
        return None
    writer = CaptureWriter(root)
    try:
        summary = writer.load_session_by_external_id(session_id)
        return summary.run_id if summary else None
    finally:
        writer.close()
