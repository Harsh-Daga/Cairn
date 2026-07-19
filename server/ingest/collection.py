"""Explicit collection modes: Manual / Efficient / Live (auto-sync ≠ browser SSE)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

CollectionMode = Literal["manual", "efficient", "live"]

MODE_HELP: dict[CollectionMode, str] = {
    "manual": "No watcher or periodic discovery; data changes only on Sync now / cairn sync.",
    "efficient": (
        "Recommended default: filesystem watch plus low-frequency rediscovery with idle backoff."
    ),
    "live": (
        "Low-latency active-session monitoring; higher resource tradeoff. "
        "Explicitly enabled; separate from browser Live updates (SSE)."
    ),
}


@dataclass(frozen=True, slots=True)
class CollectionRuntime:
    mode: CollectionMode
    watcher_enabled: bool
    refresh_enabled: bool
    poll_interval_sec: float
    refresh_interval_sec: float
    help: str

    @property
    def auto_sync_enabled(self) -> bool:
        return self.watcher_enabled or self.refresh_enabled

    @property
    def label(self) -> str:
        return self.mode.capitalize()

    @property
    def limitation(self) -> str:
        return (
            "Collection mode controls backend monitoring only. "
            "Browser Live updates (SSE) are a separate control."
        )


_RUNTIMES: dict[CollectionMode, CollectionRuntime] = {
    "manual": CollectionRuntime(
        mode="manual",
        watcher_enabled=False,
        refresh_enabled=False,
        poll_interval_sec=0.0,
        refresh_interval_sec=0.0,
        help=MODE_HELP["manual"],
    ),
    "efficient": CollectionRuntime(
        mode="efficient",
        watcher_enabled=True,
        refresh_enabled=True,
        poll_interval_sec=1.0,
        refresh_interval_sec=60.0,
        help=MODE_HELP["efficient"],
    ),
    "live": CollectionRuntime(
        mode="live",
        watcher_enabled=True,
        refresh_enabled=True,
        poll_interval_sec=0.25,
        refresh_interval_sec=10.0,
        help=MODE_HELP["live"],
    ),
}


def normalize_mode(value: str | None) -> CollectionMode:
    cleaned = (value or "efficient").strip().lower().replace("-", "_")
    if cleaned == "manual":
        return "manual"
    if cleaned == "live":
        return "live"
    if cleaned == "efficient":
        return "efficient"
    return "efficient"


def resolve_collection_runtime(mode: str | None) -> CollectionRuntime:
    return _RUNTIMES[normalize_mode(mode)]


def collection_status(
    *,
    runtime: CollectionRuntime,
    auto_sync_running: bool,
    watched_paths: int,
    sse_subscribers: int | None = None,
) -> dict[str, Any]:
    """Honest status payload separating auto-sync from browser live updates."""
    return {
        "mode": runtime.mode,
        "auto_sync": {
            "enabled": runtime.auto_sync_enabled,
            "running": auto_sync_running,
            "watched_paths": watched_paths,
            "refresh_sec": runtime.refresh_interval_sec or None,
            "poll_sec": runtime.poll_interval_sec or None,
            "help": runtime.help,
        },
        "live_updates": {
            "kind": "browser_sse",
            "subscribers": sse_subscribers,
            "help": (
                "Browser Live updates are an SSE subscription. "
                "They do not start or stop backend collection by themselves."
            ),
        },
        "sync_now": {
            "kind": "one_shot",
            "help": "Explicit cairn sync / Sync now always scans once regardless of mode.",
        },
        "limitation": (
            "Collection mode controls backend monitoring only. "
            "Do not label a browser SSE toggle as Watch if auto-sync continues."
        ),
    }
