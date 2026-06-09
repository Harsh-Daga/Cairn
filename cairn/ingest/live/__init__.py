"""Live capture tail watchers (R19.13)."""

from cairn.ingest.live.install import install_live, live_install_status, uninstall_live
from cairn.ingest.live.tail import TailWatcher, discover_tail_paths

__all__ = [
    "TailWatcher",
    "discover_tail_paths",
    "install_live",
    "live_install_status",
    "uninstall_live",
]
