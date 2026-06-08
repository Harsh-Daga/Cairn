"""cairn context — project context asset registry."""

from __future__ import annotations

import argparse
import json

from cairn.context.registry import ContextRegistry
from cairn.ingest.project_paths import resolve_git_root


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    registry = ContextRegistry(root)
    try:
        if args.context_command == "scan":
            assets = registry.scan()
            if args.json:
                print(json.dumps([a.to_dict() for a in assets], indent=2))
            else:
                print(f"Indexed {len(assets)} context assets.")
            return 0
        if args.context_command == "list":
            assets = registry.list_assets()
            if not assets:
                print("No context assets indexed. Run: cairn context scan")
                return 0
            if args.json:
                print(json.dumps([a.to_dict() for a in assets], indent=2))
                return 0
            print(f"{'PATH':<48} {'HASH':<12}  TAGS")
            print("-" * 80)
            for asset in assets:
                short_hash = asset.content_hash[:12]
                tags = ",".join(asset.tags) if asset.tags else "-"
                print(f"{asset.path_rel:<48} {short_hash:<12}  {tags}")
            return 0
        if args.context_command == "show":
            selected = registry.resolve(args.selector)
            if selected is None:
                print(f"Context asset not found: {args.selector}")
                return 1
            if args.json:
                print(json.dumps(selected.to_dict(), indent=2))
            else:
                print(f"path:   {selected.path_rel}")
                print(f"hash:   {selected.content_hash}")
                print(f"mime:   {selected.mime or '-'}")
                print(f"git:    {selected.git_blob or '-'}")
                print(f"tags:   {', '.join(selected.tags) if selected.tags else '-'}")
                print(f"updated: {selected.updated_at}")
            return 0
    finally:
        registry.close()
    return 1
