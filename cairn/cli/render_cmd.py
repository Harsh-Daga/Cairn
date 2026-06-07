"""cairn render — self-contained provenance bundle (R15)."""

from __future__ import annotations

import argparse

from cairn.render.html import render_bundle, render_capture_bundle, zip_bundle


def run(args: argparse.Namespace) -> int:
    project_root = args.project.resolve()
    out = args.output
    if out is None:
        out = project_root / "outputs" / "bundle"

    if args.run and args.session:
        print("error: use either --run or --session, not both")
        return 1

    if args.session:
        index = render_capture_bundle(
            project_root,
            args.session,
            out,
            split=args.split,
        )
    else:
        index = render_bundle(
            project_root,
            out,
            run_id=args.run,
            split=args.split,
        )
    print(f"Bundle: {index}")

    if args.zip:
        if out.name == "bundle":
            zip_path = out.with_suffix(".zip")
        else:
            zip_path = out.parent / f"{out.name}.zip"
        zip_bundle(out, zip_path)
        print(f"Zip: {zip_path}")

    return 0
