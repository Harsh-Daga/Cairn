"""cairn hook — internal hook handler (R19.8)."""

from __future__ import annotations

import argparse

from cairn.ingest.hook_cmd import run_hook


def run(args: argparse.Namespace) -> int:
    return run_hook(event=args.event, source=args.source)
