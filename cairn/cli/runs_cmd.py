"""cairn runs — list recent builds from the ledger."""

from __future__ import annotations

import argparse

from cairn.ledger.ledger import Ledger


def run(args: argparse.Namespace) -> int:
    project_root = args.project.resolve()
    db_path = project_root / ".cairn" / "ledger.db"
    if not db_path.is_file():
        print("No runs yet.")
        return 0

    ledger = Ledger(db_path)
    try:
        runs = ledger.list_runs(limit=args.limit)
        if not runs:
            print("No runs yet.")
            return 0

        print(f"{'RUN ID':<36} {'STATUS':<10} {'NODES':>6} {'COST':>10}  STARTED")
        print("-" * 80)
        for r in runs:
            cost = "—" if r.total_cost is None else f"${r.total_cost:.4f}"
            nodes = ledger.node_count(r.run_id)
            print(
                f"{r.run_id:<36} {r.status:<10} {nodes:>6} {cost:>10}  {r.started_at}"
            )
    finally:
        ledger.close()
    return 0
