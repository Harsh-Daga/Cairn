"""cairn doctor — preflight checks."""

from __future__ import annotations

import argparse

from cairn.doctor.checks import run_doctor
from cairn.loader.toml import load_project
from cairn.model.errors import CairnError


def run(args: argparse.Namespace) -> int:
    try:
        project = load_project(args.project.resolve())
    except CairnError as exc:
        print(f"doctor: cannot load project: {exc}")
        return 1
    report = run_doctor(project)
    for issue in report.issues:
        print(f"[{issue.severity}] {issue.message}")
    if report.ok:
        print("doctor: all checks passed")
        return 0
    print("doctor: failed — fix errors before build")
    return 1
