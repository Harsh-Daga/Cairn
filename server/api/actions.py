"""THE action registry — single source of CLI/UI/API parity (Phase 7)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionDef:
    """Registered action definition."""

    name: str
    title: str
    category: str
    handler: Callable[..., Any]


_REGISTRY: list[ActionDef] = []


def register_action(
    *,
    name: str,
    title: str,
    category: str,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to register an action handler."""

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        _REGISTRY.append(ActionDef(name=name, title=title, category=category, handler=fn))
        return fn

    return decorator


def list_actions() -> list[ActionDef]:
    """Return all registered actions."""
    return list(_REGISTRY)
