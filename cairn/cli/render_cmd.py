"""cairn render — self-contained provenance bundle (R15)."""

from __future__ import annotations

import argparse

from cairn.render.html import render_bundle, zip_bundle


def run(args: argparse.Namespace) -> int:
    project_root = args.project.resolve()
    out = args.output
    if out is None:
        out = project_root / "outputs" / "bundle"

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
