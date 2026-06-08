"""cairn workflow — versioned workflow execution."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cairn.cache.store import CacheStore
from cairn.executor.runner import BuildOptions
from cairn.model.errors import CairnError
from cairn.providers.registry import create_provider
from cairn.workflow.engine import WorkflowEngine, workflow_history
from cairn.workflow.loader import load_workflow


def run(args: argparse.Namespace) -> int:
    root = args.project.resolve()
    try:
        if args.workflow_command == "list":
            try:
                _, workflow = load_workflow(root)
            except CairnError:
                print("No workflows found (missing cairn.toml).")
                return 0
            workflows = [workflow]
            if args.json:
                print(json.dumps([w.to_dict() for w in workflows], indent=2))
            else:
                for wf in workflows:
                    print(f"{wf.workflow_ref}  steps={len(wf.steps)}  status={wf.status}")
            return 0

        workflow_ref = getattr(args, "ref", None)
        project, workflow = load_workflow(root, workflow_ref)
        engine = WorkflowEngine(project, workflow)

        if args.workflow_command == "validate":
            result = engine.validate()
            if args.json:
                print(
                    json.dumps(
                        {
                            "workflow_ref": result.workflow_ref,
                            "ok": result.ok,
                            "message": result.message,
                            "sources": result.source_count,
                            "steps": result.step_count,
                            "nodes": result.node_count,
                        },
                        indent=2,
                    )
                )
            else:
                if result.ok:
                    print(f"OK: {result.workflow_ref}")
                    print(
                        f"  sources={result.source_count} "
                        f"steps={result.step_count} nodes={result.node_count}"
                    )
                else:
                    print(f"FAILED: {result.message}")
            return 0 if result.ok else 1

        if args.workflow_command == "history":
            runs = workflow_history(root, limit=args.limit)
            if not runs:
                print("No workflow runs yet.")
                return 0
            if args.json:
                print(json.dumps([r.__dict__ for r in runs], indent=2))
                return 0
            print(f"{'RUN ID':<30} {'WORKFLOW':<20}  CONTEXT DIGEST")
            print("-" * 80)
            for item in runs:
                short_digest = item.context_digest[:12]
                print(f"{item.run_id:<30} {item.workflow_ref:<20}  {short_digest}")
            return 0

        if args.workflow_command == "run":
            cache = CacheStore(project.root)
            fixtures = Path(__file__).resolve().parents[1] / "data" / "fixtures"
            provider = create_provider(
                mode="recorded" if args.provider_mode == "recorded" else "live",
                fixtures_dir=fixtures,
                model=project.defaults_model,
            )
            try:
                plan = engine.plan(cache)
                if plan.work_count > 0 and not args.dry_run and not args.yes:
                    total = (
                        "unpriced"
                        if plan.has_unpriced
                        else f"${plan.total_estimated_cost:.4f}"
                    )
                    print(f"Plan: {plan.work_count} node(s), estimated cost {total}")
                    print("Re-run with --yes to confirm.")
                    return 0
                options = BuildOptions(
                    dry_run=args.dry_run,
                    yes=args.yes or args.dry_run,
                    max_cost=args.max_cost,
                )
                if args.dry_run:
                    result = engine.validate()
                    print(f"Dry run OK: {result.node_count} node(s) planned.")
                    return 0
                run_result = engine.run(cache, provider, options=options)
            finally:
                cache.close()
            if args.json:
                print(json.dumps(run_result.__dict__, indent=2))
            else:
                print(f"Workflow: {run_result.workflow_ref}")
                print(f"Run:      {run_result.run_id}")
                print(f"Context:  {run_result.context_digest[:16]}…")
                print(f"Nodes:    {run_result.node_count} ({run_result.cache_hits} cached)")
            return 0
    except (CairnError, ValueError) as exc:
        print(f"workflow error: {exc}")
        return 1
    return 1
