"""IncrementalView base + dirty-key scheduler (Phase 4)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class IncrementalView(ABC):
    """Base class for incremental analyzers."""

    view_name: str
    VERSION: int = 1

    @abstractmethod
    def keys_for(self, trace_id: str) -> list[str]:
        """Return view keys affected by a trace."""
        ...

    @abstractmethod
    def compute(self, key: str) -> None:
        """Recompute a single view key."""
        ...
