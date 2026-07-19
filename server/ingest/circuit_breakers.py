"""Ingest circuit breakers: file/parse budgets, quarantine, adaptive pause (ADR-11)."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeout
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from server.configuration import ResourcesConfig, load_config
from server.export.scrub import scrub_text
from server.util.private_files import ensure_private_dir, write_private_text
from server.util.resources import budget_status, inventory_disk

BreakerReason = Literal[
    "file_too_large",
    "parse_timeout",
    "parse_error",
    "adapter_paused",
    "disk_budget_over",
    "ok",
]


@dataclass(frozen=True, slots=True)
class BreakerDecision:
    allow: bool
    reason: BreakerReason
    detail: str
    file_bytes: int | None = None


@dataclass
class CircuitState:
    """Persisted pause / failure streaks (never mutates agent source logs)."""

    adapter_failures: dict[str, int]
    paused_adapters: dict[str, str]  # adapter_id -> reason
    quarantines: list[dict[str, Any]]
    global_pause: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_failures": dict(self.adapter_failures),
            "paused_adapters": dict(self.paused_adapters),
            "quarantines": list(self.quarantines[-50:]),
            "global_pause": self.global_pause,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CircuitState:
        return cls(
            adapter_failures={
                str(k): int(v) for k, v in (data.get("adapter_failures") or {}).items()
            },
            paused_adapters={
                str(k): str(v) for k, v in (data.get("paused_adapters") or {}).items()
            },
            quarantines=list(data.get("quarantines") or []),
            global_pause=data.get("global_pause"),
        )


def state_path(workspace_root: Path) -> Path:
    return (workspace_root / ".cairn" / "circuit_state.json").resolve()


def quarantine_root(workspace_root: Path) -> Path:
    return (workspace_root / ".cairn" / "quarantine").resolve()


def load_state(workspace_root: Path) -> CircuitState:
    path = state_path(workspace_root)
    if not path.is_file():
        return CircuitState({}, {}, [], None)
    try:
        return CircuitState.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return CircuitState({}, {}, [], None)


def save_state(workspace_root: Path, state: CircuitState) -> None:
    path = state_path(workspace_root)
    ensure_private_dir(path.parent)
    write_private_text(path, json.dumps(state.to_dict(), indent=2, sort_keys=True))


def resources_config(workspace_root: Path) -> ResourcesConfig:
    return load_config(workspace_root).resources


def assess_pre_parse(
    path: Path,
    *,
    workspace_root: Path,
    adapter_id: str,
    state: CircuitState | None = None,
) -> BreakerDecision:
    """Decide whether ingest may call parse_path (never mutates *path*)."""
    cfg = resources_config(workspace_root)
    st = state or load_state(workspace_root)
    if st.global_pause:
        return BreakerDecision(False, "disk_budget_over", st.global_pause)
    if adapter_id in st.paused_adapters:
        return BreakerDecision(
            False,
            "adapter_paused",
            st.paused_adapters[adapter_id],
        )
    # Soft disk budget over → global pause reason (caller may persist).
    disk = inventory_disk(workspace_root)
    budget = budget_status(disk["total_bytes"], cfg.soft_budget_bytes)
    if budget["status"] == "over":
        return BreakerDecision(
            False,
            "disk_budget_over",
            f"soft budget over ({budget['message']})",
        )
    try:
        if not path.is_file() or path.is_symlink():
            return BreakerDecision(False, "parse_error", "not a regular file")
        size = path.stat().st_size
    except OSError as exc:
        return BreakerDecision(False, "parse_error", f"stat failed: {exc}")
    if size > cfg.max_file_bytes:
        return BreakerDecision(
            False,
            "file_too_large",
            f"{size} bytes > max_file_bytes={cfg.max_file_bytes}",
            file_bytes=size,
        )
    return BreakerDecision(True, "ok", "within budgets", file_bytes=size)


def quarantine_path(
    workspace_root: Path,
    *,
    adapter_id: str,
    path: Path,
    reason: BreakerReason,
    detail: str,
    file_bytes: int | None = None,
) -> dict[str, Any]:
    """Record quarantine metadata + scrubbed sample; never modify the source file."""
    digest = hashlib.sha256(f"{adapter_id}:{path}".encode()).hexdigest()[:16]
    out = quarantine_root(workspace_root) / adapter_id / digest
    ensure_private_dir(out)
    sample = ""
    try:
        raw = path.read_bytes()[: 64 * 1024]
        sample = scrub_text(raw.decode("utf-8", errors="replace"), workspace_root)
    except OSError:
        sample = ""
    manifest = {
        "schema": "cairn.quarantine.v1",
        "quarantined_at": datetime.now(UTC).isoformat(),
        "adapter_id": adapter_id,
        "source_path": str(path),
        "reason": reason,
        "detail": detail,
        "file_bytes": file_bytes,
        "source_untouched": True,
        "sample_chars": len(sample),
        "limitation": (
            "Source agent logs are never rewritten. "
            "Only a scrubbed ≤64KiB sample is stored under .cairn/quarantine/."
        ),
    }
    write_private_text(out / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
    if sample:
        write_private_text(out / "sample.txt", sample)
    state = load_state(workspace_root)
    state.quarantines.append(
        {
            "adapter_id": adapter_id,
            "path": str(path),
            "reason": reason,
            "detail": detail,
            "quarantine_dir": str(out),
            "at": manifest["quarantined_at"],
        }
    )
    save_state(workspace_root, state)
    return manifest


def note_failure(
    workspace_root: Path,
    *,
    adapter_id: str,
    reason: BreakerReason,
    detail: str,
) -> CircuitState:
    cfg = resources_config(workspace_root)
    state = load_state(workspace_root)
    streak = int(state.adapter_failures.get(adapter_id, 0)) + 1
    state.adapter_failures[adapter_id] = streak
    if streak >= cfg.max_consecutive_failures:
        state.paused_adapters[adapter_id] = (
            f"paused after {streak} consecutive failures ({reason}: {detail})"
        )
    if reason == "disk_budget_over":
        state.global_pause = detail
    save_state(workspace_root, state)
    return state


def note_success(workspace_root: Path, *, adapter_id: str) -> None:
    state = load_state(workspace_root)
    if adapter_id in state.adapter_failures:
        state.adapter_failures[adapter_id] = 0
        save_state(workspace_root, state)


def resume_circuits(
    workspace_root: Path,
    *,
    adapter_id: str | None = None,
) -> dict[str, Any]:
    """Clear pause flags (explicit resume). Does not delete quarantine records."""
    state = load_state(workspace_root)
    if adapter_id:
        state.paused_adapters.pop(adapter_id, None)
        state.adapter_failures[adapter_id] = 0
    else:
        state.paused_adapters.clear()
        state.adapter_failures.clear()
        state.global_pause = None
    save_state(workspace_root, state)
    return {
        "ok": True,
        "cleared_adapter": adapter_id,
        "state": state.to_dict(),
        "limitation": "Quarantine manifests are retained for forensics until manually removed.",
    }


def circuit_status(workspace_root: Path) -> dict[str, Any]:
    state = load_state(workspace_root)
    cfg = resources_config(workspace_root)
    qroot = quarantine_root(workspace_root)
    q_count = 0
    if qroot.is_dir():
        q_count = sum(1 for p in qroot.rglob("manifest.json") if p.is_file())
    return {
        "max_file_bytes": cfg.max_file_bytes,
        "max_parse_ms": cfg.max_parse_ms,
        "max_consecutive_failures": cfg.max_consecutive_failures,
        "paused_adapters": dict(state.paused_adapters),
        "global_pause": state.global_pause,
        "adapter_failures": dict(state.adapter_failures),
        "quarantine_count": q_count,
        "recent_quarantines": state.quarantines[-10:],
        "limitation": (
            "Breakers quarantine metadata under .cairn/quarantine/ and pause "
            "offending adapters; source agent logs are never modified."
        ),
    }


def run_parse_with_budget(
    parse_fn: Callable[[], Any],
    *,
    max_parse_ms: int,
) -> tuple[Any, BreakerReason | None, str]:
    """Run parse_fn with a wall-clock timeout (thread; best-effort cancel)."""
    timeout_s = max(0.1, max_parse_ms / 1000.0)
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(parse_fn)
        try:
            result = fut.result(timeout=timeout_s)
        except FuturesTimeout:
            return None, "parse_timeout", f"exceeded {max_parse_ms}ms"
        except Exception as exc:  # noqa: BLE001 — surface as breaker, pipeline logs
            return None, "parse_error", f"{type(exc).__name__}: {exc}"
    _ = started
    return result, None, "ok"


def shield_overlay(workspace_root: Path) -> dict[str, Any]:
    """Extra shield facts/state from circuit breakers."""
    status = circuit_status(workspace_root)
    state: Literal[
        "healthy", "degraded", "paused", "quarantined", "attention", "unknown", "unavailable"
    ] = "healthy"
    if status["global_pause"] or status["paused_adapters"]:
        state = "paused"
    elif status["quarantine_count"]:
        state = "quarantined"
    elif any(v > 0 for v in status["adapter_failures"].values()):
        state = "degraded"
    facts: list[str] = []
    if status["global_pause"]:
        facts.append(f"Global ingest pause: {status['global_pause']}")
    for aid, reason in status["paused_adapters"].items():
        facts.append(f"Adapter paused ({aid}): {reason}")
    if status["quarantine_count"]:
        facts.append(f"Quarantine records: {status['quarantine_count']}")
    return {
        "state": state,
        "facts": facts,
        "circuit": status,
    }
