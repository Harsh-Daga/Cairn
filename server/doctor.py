"""cairn doctor — read-only environment and install verification."""

from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

from server import __version__
from server.analyze.git_privacy import assess_git_privacy
from server.app import static_exists
from server.config import Settings
from server.configuration import load_config
from server.ingest.parse_health import adapter_issue_url, health_payload
from server.ingest.registry import build_adapters
from server.util.private_files import permissive_paths, restrict_tree
from server.util.resources import budget_status, format_bytes, inventory_disk


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
        db_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        probe = db_dir / ".write_probe"
        descriptor = os.open(probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        probe.unlink()
        ok = True
        detail = str(db_dir)
    except OSError as exc:
        ok = False
        detail = str(exc)
    fix = f"Ensure {db_dir} is writable" if not ok else None
    return CheckResult("DB directory writable", ok, detail, fix)


def _check_permissions(workspace: Path | None, *, repair: bool = False) -> CheckResult:
    """Check and optionally repair Cairn-owned sensitive directory trees."""
    if os.name == "nt":
        return CheckResult(
            "Private file permissions",
            True,
            "Unix modes not applicable; protect Cairn paths with the current user's ACL",
            None,
        )
    root = (workspace or Path.cwd()).resolve()
    trees = [root / ".cairn", Path.home() / ".cairn"]
    existing = [path for path in trees if path.exists() and not path.is_symlink()]
    if repair:
        for path in existing:
            restrict_tree(path)
    issues = [issue for path in existing for issue in permissive_paths(path)]
    if not issues:
        detail = (
            "no Cairn data directories yet"
            if not existing
            else f"{len(existing)} sensitive tree(s) are owner-only"
        )
        return CheckResult("Private file permissions", True, detail, None)
    samples = ", ".join(f"{path} ({actual:04o})" for path, actual, _expected in issues[:3])
    if len(issues) > 3:
        samples += f", and {len(issues) - 3} more"
    return CheckResult(
        "Private file permissions",
        False,
        samples,
        "Run: cairn doctor --repair-permissions",
    )


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


def _check_adapter_health(workspace: Path | None) -> CheckResult:
    root = (workspace or Path.cwd()).resolve()
    db_path = root / ".cairn" / "cairn.db"
    if not db_path.is_file():
        return CheckResult("Adapter parse health", True, "no parse history yet", None)
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM adapter_parse_health ORDER BY adapter_id").fetchall()
        conn.close()
    except sqlite3.Error:
        return CheckResult("Adapter parse health", True, "no parse history yet", None)
    unhealthy = [(str(row["adapter_id"]), health_payload(row)) for row in rows]
    unhealthy = [(adapter_id, health) for adapter_id, health in unhealthy if health["warning"]]
    if not unhealthy:
        return CheckResult("Adapter parse health", True, f"{len(rows)} adapter(s) healthy", None)
    adapter_id, health = unhealthy[0]
    coverage = float(health["parse_coverage"] or 0.0)
    detail = (
        f"{adapter_id} log format may have changed; numbers may be incomplete "
        f"({coverage:.0%} fully parsed)"
    )
    return CheckResult(
        "Adapter parse health",
        False,
        detail,
        f"Open an adapter issue: {adapter_issue_url(adapter_id)}",
    )


def _check_database_integrity(workspace: Path | None) -> CheckResult:
    """Report SQLite corruption without attempting a repair or mutation."""
    root = (workspace or Path.cwd()).resolve()
    db_path = root / ".cairn" / "cairn.db"
    if not db_path.is_file():
        return CheckResult("Database integrity", True, "no database yet", None)
    try:
        conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        result = conn.execute("PRAGMA quick_check").fetchone()
        foreign_key_issues = conn.execute(
            "SELECT * FROM pragma_foreign_key_check LIMIT 5"
        ).fetchall()
        conn.close()
    except sqlite3.DatabaseError as exc:
        return CheckResult(
            "Database integrity",
            False,
            f"unreadable or corrupt: {exc}",
            "Restore a verified backup; preserve the damaged file for diagnosis",
        )
    quick_ok = result is not None and str(result[0]).lower() == "ok"
    ok = quick_ok and not foreign_key_issues
    if not quick_ok:
        detail = f"quick_check: {result[0] if result else 'no result'}"
    elif foreign_key_issues:
        table, rowid, parent, _fk_index = foreign_key_issues[0]
        detail = f"foreign_key_check: {table} row {rowid} references missing {parent}"
    else:
        detail = "quick_check: ok; foreign_key_check: ok"
    return CheckResult(
        "Database integrity",
        ok,
        detail,
        None if ok else "Restore a verified backup; do not overwrite the damaged database",
    )


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
    if found:
        return CheckResult("MCP config", True, ", ".join(found), None)
    return CheckResult(
        "MCP config",
        True,
        "not configured (optional; run: cairn mcp install)",
        None,
    )


def _check_disk_inventory(workspace: Path | None) -> CheckResult:
    """Advisory soft-budget check against measured `.cairn` inventory."""
    root = (workspace or Path.cwd()).resolve()
    disk = inventory_disk(root)
    total = int(disk["total_bytes"])
    soft = load_config(root).resources.soft_budget_bytes
    budget = budget_status(total, soft)
    detail = (
        f"{format_bytes(total)} in .cairn — {budget['message']}"
        if (root / ".cairn").exists()
        else "no .cairn directory yet"
    )
    if budget["status"] == "over":
        return CheckResult(
            "Disk soft budget",
            False,
            detail,
            "Raise [resources].soft_budget_bytes or run cleanup after confirmation "
            "(cairn resource --json)",
        )
    return CheckResult("Disk soft budget", True, detail, None)


def _check_git_privacy(workspace: Path | None) -> CheckResult:
    """Warn when `.cairn/` is tracked or not ignored in a git work tree."""
    root = (workspace or Path.cwd()).resolve()
    report = assess_git_privacy(root)
    if report.kind == "ok":
        return CheckResult("Git privacy", True, report.message, None)
    fix = (
        "Run: cairn action git_exclude_cairn --params-json '{\"approve\": true}' "
        "(or untrack existing .cairn paths)"
    )
    return CheckResult("Git privacy", False, report.message, fix)


def _check_pricing(workspace: Path | None) -> CheckResult:
    """Surface bundled price provenance and staleness (offline; never downloads)."""
    from server.ingest.pricing import pricing_status

    root = (workspace or Path.cwd()).resolve()
    status = pricing_status(root)
    detail = (
        f"v{status['version']} effective {status['effective_date']} "
        f"({status['model_count']} models; overrides={status['override_count']})"
    )
    if status["stale"]:
        return CheckResult(
            "Model pricing",
            False,
            f"stale — {detail}; age {status['age_days']}d > {status['stale_after_days']}d",
            "Set [pricing.overrides.<model>] locally, or raise pricing.stale_after_days "
            "after reviewing vendor rates (Cairn never auto-downloads prices)",
        )
    return CheckResult("Model pricing", True, detail, None)


def _check_egress(workspace: Path | None) -> CheckResult:
    """Report Cairn-initiated egress ledger size (informational; empty is healthy)."""
    from server.util.egress import egress_status

    root = (workspace or Path.cwd()).resolve()
    status = egress_status(root)
    count = int(status.get("entry_count") or 0)
    detail = f"{count} recorded attempt(s); default flows expect empty"
    return CheckResult("Egress ledger", True, detail, None)


def run_doctor(
    *,
    workspace: Path | None = None,
    port: int = 8787,
    repair_permissions: bool = False,
) -> list[CheckResult]:
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
        _check_permissions(workspace, repair=repair_permissions),
        _check_disk_inventory(workspace),
        _check_git_privacy(workspace),
        _check_pricing(workspace),
        _check_egress(workspace),
        _check_adapters(workspace),
        _check_adapter_health(workspace),
        _check_database_integrity(workspace),
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


def print_doctor(
    *,
    workspace: Path | None = None,
    port: int = 8787,
    as_json: bool = False,
    repair_permissions: bool = False,
) -> int:
    results = run_doctor(
        workspace=workspace,
        port=port,
        repair_permissions=repair_permissions,
    )
    if as_json:
        print(json.dumps(doctor_json(results), indent=2))
    else:
        print(format_doctor_table(results))
    return 0 if all(r.ok for r in results) else 1
