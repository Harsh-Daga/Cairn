"""cairn help — list unified command groups."""

from __future__ import annotations

import argparse

from cairn.cli.groups import COMMAND_GROUPS


def run(args: argparse.Namespace) -> int:
    print("Cairn command groups:\n")
    for group, commands in COMMAND_GROUPS.items():
        print(f"  {group}")
        print(f"    {' | '.join(commands)}")
        print()
    if args.verbose:
        print("Run `cairn <command> --help` for command-specific usage.")
    return 0
