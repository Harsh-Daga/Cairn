"""cairn snapshot — point-in-time project snapshots."""

from __future__ import annotations

import argparse
import json

from cairn.ingest.project_paths import resolve_git_root
from cairn.snapshot.engine import (
    create_snapshot,
    diff_snapshots,
    list_snapshots,
    restore_snapshot,
)


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project

    if args.snapshot_command == "create":
        try:
            manifest = create_snapshot(root, label=args.label)
        except FileNotFoundError as exc:
            print(str(exc))
            return 1
        if args.json:
            print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"Snapshot {manifest.snapshot_id}")
            if manifest.label:
                print(f"  label: {manifest.label}")
            print(f"  sessions: {len(manifest.sessions)}")
            print(f"  cas objects: {len(manifest.cas_hashes)}")
        return 0

    if args.snapshot_command == "list":
        manifests = list_snapshots(root)
        if not manifests:
            print("No snapshots.")
            return 0
        if args.json:
            print(json.dumps([m.to_dict() for m in manifests], indent=2, sort_keys=True))
            return 0
        print(f"{'ID':<36} {'CREATED':<26}  SESSIONS")
        print("-" * 72)
        for manifest in manifests:
            label = f" ({manifest.label})" if manifest.label else ""
            print(
                f"{manifest.snapshot_id:<36} {manifest.created_at:<26}  "
                f"{len(manifest.sessions)}{label}"
            )
        return 0

    if args.snapshot_command == "diff":
        try:
            diff = diff_snapshots(root, args.left, args.right)
        except FileNotFoundError as exc:
            print(str(exc))
            return 1
        if args.json:
            print(json.dumps(diff, indent=2, sort_keys=True))
        else:
            print(f"Comparing {args.left} → {args.right}")
            print(f"  sessions added:   {len(diff['sessions_added'])}")
            print(f"  sessions removed: {len(diff['sessions_removed'])}")
            print(f"  cas added:        {len(diff['cas_added'])}")
            if diff["git_commit_changed"]:
                print(f"  git: {diff['left_git_commit']} → {diff['right_git_commit']}")
        return 0

    if args.snapshot_command == "restore":
        try:
            manifest = restore_snapshot(root, args.snapshot_id)
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc))
            return 1
        if args.json:
            print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"Restored snapshot {manifest.snapshot_id}")
            print(f"  sessions: {len(manifest.sessions)}")
        return 0

    return 1
