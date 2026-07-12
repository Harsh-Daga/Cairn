#!/usr/bin/env python3
"""Release readiness checks for Cairn."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PYPROJECT = ROOT / "pyproject.toml"
SERVER_INIT = ROOT / "server" / "__init__.py"

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
    if pyproject_version != server_version:
        raise ValueError(f"version mismatch: pyproject={pyproject_version} server={server_version}")
    print(f"version sync ok: {pyproject_version}")


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


def check_doctor_on_wheel() -> None:
    with tempfile.TemporaryDirectory(prefix="cairn-release-check-") as tmp:
        tmp_path = Path(tmp)
        dist_dir = tmp_path / "dist"
        work_dir = tmp_path / "workspace"
        venv = tmp_path / "venv"
        dist_dir.mkdir(parents=True, exist_ok=True)
        work_dir.mkdir(parents=True, exist_ok=True)

        _run(["uv", "run", "python", "scripts/build_ui.py"])
        _run(["uv", "build", "--wheel", "--out-dir", str(dist_dir)])
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
        _run([str(cairn), "doctor", "--workspace", str(work_dir), "--json"], env=env)
        print(f"wheel doctor ok: {wheel.name}")


def main() -> int:
    check_version_sync()
    check_readme_assets()
    check_readme_links()
    check_doctor_on_wheel()
    print("release_check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
