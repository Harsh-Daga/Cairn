#!/usr/bin/env python3
"""Single local release gate for Cairn.

Default mode runs the complete readiness matrix (lint, types, tests, UI, browser,
generated-artifact drift, packaging, clean-wheel doctor). Use ``--packaging-only``
for the lighter metadata/wheel path already exercised in CI packaging jobs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
SERVER_INIT = ROOT / "server" / "__init__.py"
GITHUB_DIR = ROOT / ".github"
UI_PACKAGE = ROOT / "ui" / "package.json"
UI_LOCK = ROOT / "ui" / "package-lock.json"
UV_LOCK = ROOT / "uv.lock"
CHANGELOG = ROOT / "CHANGELOG.md"
CITATION = ROOT / "CITATION.cff"
GENERATED = (
    ROOT / "ACCURACY.md",
    ROOT / "server" / "ingest" / "accuracy_data.json",
    ROOT / "docs" / "cli.md",
    ROOT / "ui" / "src" / "lib" / "generated" / "api-types.ts",
    ROOT / "docs" / "api" / "openapi-compat.json",
    ROOT / "docs" / "api" / "generated.md",
    ROOT / "docs" / "configuration-reference.md",
)

VERSION_RE = re.compile(r'^version\s*=\s*"([^"]+)"\s*$')
SERVER_VERSION_RE = re.compile(r'^__version__\s*=\s*"([^"]+)"\s*$')
LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
IMG_SRC_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
MARKDOWN_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)(?:\s+[^)]*)?\)")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_version(text: str, pattern: re.Pattern[str], label: str) -> str:
    for line in text.splitlines():
        match = pattern.match(line.strip())
        if match:
            return match.group(1)
    raise ValueError(f"missing {label} version")


def check_version_sync() -> None:
    pyproject_version = _extract_version(_read_text(PYPROJECT), VERSION_RE, "pyproject")
    server_version = _extract_version(_read_text(SERVER_INIT), SERVER_VERSION_RE, "server")
    ui_package = json.loads(_read_text(UI_PACKAGE))
    ui_lock = json.loads(_read_text(UI_LOCK))
    uv_document = tomllib.loads(_read_text(UV_LOCK))
    root_lock = next(
        package for package in uv_document["package"] if package["name"] == "cairn-workspace"
    )
    versions = {
        "pyproject": pyproject_version,
        "server": server_version,
        "ui package": str(ui_package["version"]),
        "ui lock": str(ui_lock["packages"][""]["version"]),
        "uv lock": str(root_lock["version"]),
        "citation": str(yaml.safe_load(_read_text(CITATION))["version"]),
    }
    if len(set(versions.values())) != 1:
        raise ValueError(f"version mismatch: {versions}")
    readme = _read_text(README)
    docs_readme = _read_text(ROOT / "docs" / "README.md")
    if (
        f"version-{pyproject_version}-" not in readme
        or f"Version {pyproject_version}" not in readme
    ):
        raise ValueError("README version badge and alt text are stale")
    if f"current {pyproject_version} " not in docs_readme:
        raise ValueError("docs/README.md current-version statement is stale")
    if f"## [{pyproject_version}]" not in _read_text(CHANGELOG):
        raise ValueError(f"CHANGELOG.md has no {pyproject_version} entry")
    print(f"version sync ok: {pyproject_version}")


def check_changelog() -> None:
    version = _extract_version(_read_text(PYPROJECT), VERSION_RE, "pyproject")
    text = _read_text(CHANGELOG)
    if not re.search(
        rf"^\[{re.escape(version)}\]: https://github\.com/Harsh-Daga/Cairn/compare/v[^.]+"
        rf".*v{re.escape(version)}$",
        text,
        re.MULTILINE,
    ):
        raise ValueError(f"CHANGELOG.md is missing the {version} compare link")
    print("changelog entry and compare link ok")


def check_readme_assets() -> None:
    readme = _read_text(README)
    sources = [*IMG_SRC_RE.findall(readme), *MARKDOWN_IMAGE_RE.findall(readme)]
    missing: list[str] = []
    for src in sources:
        if src.startswith("https://raw.githubusercontent.com/"):
            tail = src.split("/main/", 1)[-1]
            local = ROOT / tail
            if not local.is_file():
                missing.append(tail)
        elif not src.startswith(("http://", "https://", "data:")):
            local = ROOT / src.split("#", 1)[0]
            if not local.is_file():
                missing.append(src)
    if missing:
        listing = "\n".join(f"- {item}" for item in sorted(set(missing)))
        raise ValueError(f"README references missing image assets:\n{listing}")
    print("readme assets ok")


def check_readme_links() -> None:
    readme = _read_text(README)
    missing: list[str] = []
    for target in LINK_RE.findall(readme):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        local = (ROOT / target).resolve()
        if not local.exists():
            missing.append(target)
    if missing:
        listing = "\n".join(f"- {item}" for item in sorted(set(missing)))
        raise ValueError(f"README has missing local links:\n{listing}")
    print("readme links ok")


def check_github_yaml() -> None:
    """Ensure workflow and issue-template YAML can be loaded by GitHub."""
    paths = sorted([*GITHUB_DIR.rglob("*.yml"), *GITHUB_DIR.rglob("*.yaml")])
    for path in paths:
        try:
            yaml.safe_load(_read_text(path))
        except yaml.YAMLError as exc:
            relative = path.relative_to(ROOT)
            raise ValueError(f"invalid GitHub YAML: {relative}: {exc}") from exc
    print(f"github yaml ok: {len(paths)} file(s)")


def check_generated_artifacts() -> None:
    before = {path: path.read_bytes() for path in GENERATED}
    _run([sys.executable, "scripts/gen_accuracy.py"])
    _run([sys.executable, "scripts/gen_cli_docs.py"])
    _run([sys.executable, "scripts/generate_config_reference.py"])
    _run([sys.executable, "scripts/build_ui.py", "types"])
    changed = [
        str(path.relative_to(ROOT))
        for path, content in before.items()
        if path.read_bytes() != content
    ]
    if changed:
        raise ValueError(f"generated artifacts were stale: {', '.join(changed)}")
    print("generated artifacts current")


def _forbidden_archive_name(name: str) -> bool:
    parts = Path(name).parts
    return (
        any(
            part in {"AGENTS.md", ".hypothesis", "node_modules", ".git", "test-results"}
            for part in parts
        )
        or "docs/plans" in name
    )


def check_archive_contents(dist_dir: Path) -> None:
    wheels = sorted(dist_dir.glob("*.whl"))
    sdists = sorted(dist_dir.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("release build must produce exactly one wheel and one sdist")
    with zipfile.ZipFile(wheels[0]) as archive:
        names = archive.namelist()
        required = (
            "server/static/index.html",
            "server/static/theme-bootstrap.js",
            "server/static_file/index.html",
            "server/static_file/theme-bootstrap.js",
            "dist-info/licenses/LICENSE",
            "dist-info/licenses/THIRD_PARTY_NOTICES.md",
            "dist-info/licenses/licenses/OFL-1.1.txt",
        )
        for suffix in required:
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f"wheel is missing {suffix}")
        if not any(
            name.startswith("server/static/assets/") and name.endswith(".js") for name in names
        ):
            raise ValueError("wheel is missing the built JavaScript application")
        if not any(
            name.startswith("server/static_file/assets/") and name.endswith(".js") for name in names
        ):
            raise ValueError("wheel is missing the file-compatible static-export application")
        metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
        metadata = archive.read(metadata_name).decode("utf-8")
        if "License-Expression: Apache-2.0" not in metadata:
            raise ValueError("wheel metadata is missing the SPDX license expression")
        if any(_forbidden_archive_name(name) for name in names):
            raise ValueError("wheel contains private or development-only files")
    with tarfile.open(sdists[0], "r:gz") as archive:
        names = archive.getnames()
        for suffix in (
            "/README.md",
            "/pyproject.toml",
            "/LICENSE",
            "/THIRD_PARTY_NOTICES.md",
            "/licenses/OFL-1.1.txt",
            "/server/static/index.html",
            "/server/static/theme-bootstrap.js",
            "/server/static_file/index.html",
            "/server/static_file/theme-bootstrap.js",
        ):
            if not any(name.endswith(suffix) for name in names):
                raise ValueError(f"sdist is missing {suffix}")
        forbidden = [name for name in names if _forbidden_archive_name(name)]
        if forbidden:
            raise ValueError(f"sdist contains private/development files: {forbidden[:3]}")
    print("wheel and sdist metadata/contents ok")


def check_offline_static_assets() -> None:
    index = _read_text(ROOT / "server" / "static" / "index.html")
    remote_asset = re.compile(r"""(?:src|href)=["']https?://""", re.IGNORECASE)
    if remote_asset.search(index):
        raise ValueError("built UI references a remote script, style, font, image, or icon")
    print("offline static asset references ok")


def check_release_workflow() -> None:
    text = _read_text(GITHUB_DIR / "workflows" / "publish.yml")
    required = (
        'tags: ["v*"]',
        "scripts/validate_release_tag.py",
        "actions/attest-build-provenance@",
        "pypa/gh-action-pypi-publish@",
        "environment: pypi",
        "SHA256SUMS",
        "cyclonedx-json",
    )
    missing = [item for item in required if item not in text]
    if missing or "branches:" in text:
        raise ValueError(f"release workflow invariants failed; missing={missing}")
    action_refs = re.findall(r"uses:\s+([^@\s]+)@([^\s#]+)", text)
    if any(not re.fullmatch(r"[0-9a-f]{40}", ref) for _, ref in action_refs):
        raise ValueError("release workflow contains a non-pinned action")
    print("release workflow trigger, permission, and provenance invariants ok")


def check_stale_packaging_text() -> None:
    paths = (
        ROOT / "README.md",
        ROOT / "CHANGELOG.md",
        ROOT / "packaging" / "homebrew" / "README.md",
    )
    stale = re.compile(r"after the first PyPI release|future first release", re.IGNORECASE)
    hits = [
        str(path.relative_to(ROOT))
        for path in paths
        if path.is_file() and stale.search(_read_text(path))
    ]
    if hits:
        raise ValueError(f"stale release text remains in: {', '.join(hits)}")
    print("stale packaging text absent")


def _run(cmd: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    proc = subprocess.run(
        cmd,
        cwd=str(cwd or ROOT),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"command failed ({' '.join(cmd)}):\n{proc.stdout}\n{proc.stderr}".strip()
        )


def check_quality_gates(*, skip_e2e: bool) -> None:
    """Deterministic quality matrix required before a release PR merges."""
    _run(["uv", "run", "ruff", "check", "."])
    _run(["uv", "run", "ruff", "format", "--check", "."])
    _run(["uv", "run", "mypy", "--strict", "server"])
    _run(["uv", "run", "pytest", "-q"])
    ui = ROOT / "ui"
    _run(["npm", "run", "lint"], cwd=ui)
    _run(["npm", "run", "format:check"], cwd=ui)
    _run(["npm", "run", "typecheck"], cwd=ui)
    _run(["npm", "run", "test"], cwd=ui)
    _run(["npm", "run", "check:api"], cwd=ui)
    _run(["uv", "run", "python", "scripts/build_ui.py", "build"])
    _run(["uv", "run", "python", "scripts/check_bundle_size.py"])
    if skip_e2e:
        print("quality gates ok (browser e2e skipped)")
        return
    _run(["npm", "run", "test:e2e"], cwd=ui)
    print("quality gates ok (including browser e2e)")


def check_reproducibility_assessment() -> None:
    _run([sys.executable, "scripts/check_reproducibility.py"])
    print("reproducibility assessment ok")


def check_doctor_on_wheel() -> None:
    with tempfile.TemporaryDirectory(prefix="cairn-release-check-") as tmp:
        tmp_path = Path(tmp)
        dist_dir = tmp_path / "dist"
        work_dir = tmp_path / "workspace"
        home_dir = tmp_path / "home"
        venv = tmp_path / "venv"
        dist_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)
        home_dir.mkdir(parents=True, exist_ok=True)

        _run(["uv", "run", "python", "scripts/build_ui.py", "build"])
        _run(["uv", "build", "--out-dir", str(dist_dir)])
        check_archive_contents(dist_dir)
        wheels = sorted(dist_dir.glob("*.whl"))
        if not wheels:
            raise ValueError("no wheel produced")
        wheel = wheels[0]

        _run([sys.executable, "-m", "venv", str(venv)])
        pip = venv / "bin" / "pip"
        cairn = venv / "bin" / "cairn"
        _run([str(pip), "install", str(wheel)])
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        env["PATH"] = f"{venv / 'bin'}:{env.get('PATH', '')}"
        env["HOME"] = str(home_dir)
        env["XDG_CONFIG_HOME"] = str(home_dir / ".config")
        env["XDG_STATE_HOME"] = str(home_dir / ".local" / "state")
        _run(
            [str(venv / "bin" / "python"), "-c", "import server; print(server.__version__)"],
            env=env,
        )
        _run([str(cairn), "--version"], env=env)
        _run([str(cairn), "doctor", "--workspace", str(work_dir), "--json"], env=env)
        print(f"wheel doctor ok: {wheel.name}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--packaging-only",
        action="store_true",
        help="Skip lint/test/e2e matrix; run version/docs/packaging/wheel checks only",
    )
    parser.add_argument(
        "--skip-e2e",
        action="store_true",
        help="Skip Playwright when running the full gate (local only; forbidden in CI)",
    )
    parser.add_argument(
        "--skip-reproducibility",
        action="store_true",
        help="Skip the two-build reproducibility assessment (local only; forbidden in CI)",
    )
    args = parser.parse_args(argv)

    in_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
    if in_ci and (args.skip_e2e or args.skip_reproducibility):
        raise SystemExit(
            "CI forbids --skip-e2e / --skip-reproducibility; "
            "use --packaging-only for packaging jobs, or run the full gate"
        )

    if not args.packaging_only:
        check_quality_gates(skip_e2e=args.skip_e2e)

    check_version_sync()
    check_changelog()
    check_readme_assets()
    check_readme_links()
    check_github_yaml()
    check_generated_artifacts()
    check_offline_static_assets()
    check_release_workflow()
    check_stale_packaging_text()
    check_doctor_on_wheel()
    if not args.packaging_only and not args.skip_reproducibility:
        check_reproducibility_assessment()

    if args.packaging_only:
        print("release_check passed (packaging-only)")
    elif args.skip_e2e or args.skip_reproducibility:
        skipped = []
        if args.skip_e2e:
            skipped.append("e2e")
        if args.skip_reproducibility:
            skipped.append("reproducibility")
        print(f"release_check passed (skipped: {', '.join(skipped)})")
    else:
        print("release_check passed (full gate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
