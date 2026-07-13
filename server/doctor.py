"""cairn doctor — read-only environment and install verification."""

from __future__ import annotations

import json
import shutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from server import __version__
from server.app import static_exists
from server.config import Settings
from server.ingest.registry import build_adapters


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    fix: str | None = None


def _check_python() -> CheckResult:
    ok = sys.version_info >= (3, 11)
    detail = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    fix = "Install Python 3.11 or newer" if not ok else None
    return CheckResult("Python >=3.11", ok, detail, fix)


def _check_cairn_on_path() -> CheckResult:
    cairn = shutil.which("cairn")
    ok = cairn is not None
    detail = cairn or "not found on PATH"
    fix = 'Add uv tool dir to PATH: export PATH="$(uv tool dir --bin):$PATH"' if not ok else None
    return CheckResult("cairn on PATH", ok, detail, fix)


def _check_version() -> CheckResult:
    detail = __version__
    ok = True
    fix = None
    return CheckResult("Cairn package version", ok, detail, fix)


def _detect_install_method() -> CheckResult:
    cairn = shutil.which("cairn")
    if not cairn:
        return CheckResult("Install method", False, "unknown", "Run scripts/install.sh")
    resolved = Path(cairn).resolve()
    text = str(resolved)
    if ".local/share/uv/tools" in text or ".local\\share\\uv\\tools" in text:
        method = "uv tool"
    elif "pipx" in text:
        method = "pipx"
    elif ".local" in text:
        method = "pip --user"
    else:
        method = "other"
    return CheckResult("Install method", True, method, None)


def _check_legacy_shim() -> CheckResult:
    cairn = shutil.which("cairn")
    if not cairn:
        return CheckResult("CLI entrypoint", True, "n/a", None)
    try:
        text = Path(cairn).read_text(encoding="utf-8", errors="ignore")[:800]
    except OSError:
        return CheckResult("CLI entrypoint", True, cairn, None)
    if "cairn.cli" in text or "from cairn import" in text:
        return CheckResult(
            "CLI entrypoint",
            False,
            f"legacy CLI shim at {cairn}",
            "Reinstall: uv tool install --force cairn-workspace  (or use: uv run cairn …)",
        )
    return CheckResult("CLI entrypoint", True, cairn, None)


def _check_port(port: int = 8787) -> CheckResult:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        in_use = sock.connect_ex(("127.0.0.1", port)) == 0
    ok = not in_use
    detail = f"port {port} {'in use' if in_use else 'free'}"
    fix = f"Use --port {port + 1} or stop the process on {port}" if not ok else None
    return CheckResult("Default port free", ok, detail, fix)


def _check_db_writable(workspace: Path | None) -> CheckResult:
    root = (workspace or Path.cwd()).resolve()
    db_dir = root / ".cairn"
    try:
        db_dir.mkdir(parents=True, exist_ok=True)
        probe = db_dir / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        ok = True
        detail = str(db_dir)
    except OSError as exc:
        ok = False
        detail = str(exc)
    fix = f"Ensure {db_dir} is writable" if not ok else None
    return CheckResult("DB directory writable", ok, detail, fix)


def _check_static_assets() -> CheckResult:
    ok = static_exists()
    detail = "server/static/index.html present" if ok else "UI not bundled"
    fix = "Run: python scripts/build_ui.py" if not ok else None
    return CheckResult("Static UI assets", ok, detail, fix)


def _check_adapters(workspace: Path | None) -> CheckResult:
    root = (workspace or Path.cwd()).resolve()
    adapters = build_adapters(root, "doctor-scan")
    paths = [ref.path for adapter in adapters for ref in adapter.detect()]
    count = len(paths)
    ok = True
    detail = f"{count} stream(s) detected"
    return CheckResult("Adapters detected", ok, detail, None)


def _check_mcp_config() -> CheckResult:
    candidates = [
        Path.home() / ".cursor" / "mcp.json",
        Path.home() / ".config" / "claude" / "claude_desktop_config.json",
        Path.home() / ".codex" / "config.toml",
    ]
    found: list[str] = []
    for path in candidates:
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "cairn" in text.lower():
            found.append(str(path))
    ok = bool(found)
    detail = ", ".join(found) if found else "no cairn MCP entry found"
    fix = "Run: cairn mcp install" if not ok else None
    return CheckResult("MCP config", ok, detail, fix)


def run_doctor(*, workspace: Path | None = None, port: int = 8787) -> list[CheckResult]:
    """Run all doctor checks and return results."""
    _ = Settings()  # validate settings module loads
    return [
        _check_python(),
        _check_cairn_on_path(),
        _check_legacy_shim(),
        _check_version(),
        _detect_install_method(),
        _check_port(port),
        _check_db_writable(workspace),
        _check_adapters(workspace),
        _check_static_assets(),
        _check_mcp_config(),
    ]


def format_doctor_table(results: list[CheckResult]) -> str:
    lines = ["", f"Cairn doctor v{__version__}", ""]
    for result in results:
        mark = "✓" if result.ok else "✗"
        lines.append(f"  {mark} {result.name:<22} {result.detail}")
        if not result.ok and result.fix:
            lines.append(f"      fix: {result.fix}")
    failed = sum(1 for r in results if not r.ok)
    lines.append("")
    lines.append(f"{len(results) - failed}/{len(results)} checks passed")
    return "\n".join(lines)


def doctor_json(results: list[CheckResult]) -> dict[str, object]:
    return {
        "version": __version__,
        "ok": all(r.ok for r in results),
        "checks": [{"name": r.name, "ok": r.ok, "detail": r.detail, "fix": r.fix} for r in results],
    }


def print_doctor(*, workspace: Path | None = None, port: int = 8787, as_json: bool = False) -> int:
    results = run_doctor(workspace=workspace, port=port)
    if as_json:
        print(json.dumps(doctor_json(results), indent=2))
    else:
        print(format_doctor_table(results))
    return 0 if all(r.ok for r in results) else 1
