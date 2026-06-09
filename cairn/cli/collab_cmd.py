"""cairn collab — file-based sync export/import."""

from __future__ import annotations

import argparse
import json

from cairn.collab.cursor import load_cursor
from cairn.collab.export import export_sync_bundle
from cairn.collab.import_bundle import import_sync_bundle
from cairn.ingest.project_paths import resolve_git_root


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project

    if args.collab_command == "export":
        try:
            manifest = export_sync_bundle(root, args.dest, project_label=args.label)
        except (FileNotFoundError, FileExistsError) as exc:
            print(str(exc))
            return 1
        if args.json:
            print(json.dumps(manifest.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"Exported {len(manifest.sessions)} sessions to {args.dest.resolve()}")
            print(f"Ledger sha256: {manifest.ledger_sha256[:16]}…")
        return 0

    if args.collab_command == "import":
        try:
            result = import_sync_bundle(root, args.source)
        except (FileNotFoundError, ValueError) as exc:
            print(str(exc))
            return 1
        if args.json:
            print(
                json.dumps(
                    {
                        "sessions_imported": result.sessions_imported,
                        "runs_inserted": result.runs_inserted,
                        "events_inserted": result.events_inserted,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
        else:
            print(
                f"Imported {result.runs_inserted} runs, "
                f"{result.events_inserted} events, "
                f"{result.sessions_imported} session mirrors."
            )
        return 0

    if args.collab_command == "status":
        cursor = load_cursor(root)
        if args.json:
            print(json.dumps(cursor.to_dict(), indent=2, sort_keys=True))
        else:
            print(f"Last sync: {cursor.last_sync_at or 'never'}")
            print(f"Sessions tracked: {cursor.session_count}")
            print(f"Last exported run: {cursor.last_exported_run_id or '-'}")
        return 0

    return 1
