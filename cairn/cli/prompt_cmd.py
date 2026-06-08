"""cairn prompt — versioned prompt library."""

from __future__ import annotations

import argparse
import json

from cairn.ingest.project_paths import resolve_git_root
from cairn.prompts.registry import PromptRegistry, parse_prompt_ref


def run(args: argparse.Namespace) -> int:
    project = args.project.resolve()
    root = resolve_git_root(project) or project
    registry = PromptRegistry(root)
    try:
        if args.prompt_command == "sync":
            entries = registry.sync()
            if args.json:
                print(json.dumps([e.to_dict() for e in entries], indent=2))
            else:
                print(f"Registered {len(entries)} new prompt version(s).")
            return 0
        if args.prompt_command == "list":
            entries = registry.list_entries()
            if not entries:
                print("No prompts registered. Run: cairn prompt sync")
                return 0
            if args.json:
                print(json.dumps([e.to_dict() for e in entries], indent=2))
                return 0
            print(f"{'PROMPT':<28} {'VERSION':<8}  PATH")
            print("-" * 72)
            for entry in entries:
                print(f"{entry.name:<28} {entry.version:<8}  {entry.path_rel}")
            return 0
        if args.prompt_command == "show":
            name, version = parse_prompt_ref(args.ref)
            selected = registry.get(name, version)
            if selected is None:
                print(f"Prompt not found: {args.ref}")
                return 1
            if args.json:
                payload = selected.to_dict()
                payload["body"] = selected.body
                print(json.dumps(payload, indent=2))
            else:
                print(f"ref:     {selected.prompt_ref}")
                print(f"path:    {selected.path_rel}")
                print(f"hash:    {selected.content_hash}")
                print(f"model:   {selected.model_override or '-'}")
                print(f"params:  {selected.params or '-'}")
                print("---")
                print(selected.body.rstrip())
            return 0
        if args.prompt_command == "diff":
            diff_text = registry.diff(args.left, args.right)
            if not diff_text:
                print("No differences.")
            else:
                print(diff_text, end="")
            return 0
    finally:
        registry.close()
    return 1
