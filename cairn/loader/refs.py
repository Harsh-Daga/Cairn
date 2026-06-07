"""Parse source()/ref() dependency expressions."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

_REF_EXPR_RE = re.compile(
    r"""^(?:source|ref)\s*\(\s*['"]([^'"]+)['"]\s*\)$""",
    re.VERBOSE,
)
_TEMPLATE_REF_RE = re.compile(
    r"""(?:source|ref)\s*\(\s*['"]([^'"]+)['"]\s*\)""",
)


@dataclass(frozen=True)
class DepRef:
    kind: Literal["source", "ref"]
    name: str


def parse_dep_expr(expr: str) -> DepRef:
    match = _REF_EXPR_RE.match(expr.strip())
    if not match:
        msg = f"invalid dependency expression: {expr!r} (expected source('x') or ref('y'))"
        raise ValueError(msg)
    name = match.group(1)
    if expr.strip().startswith("source"):
        return DepRef(kind="source", name=name)
    return DepRef(kind="ref", name=name)


def find_template_refs(template: str) -> list[DepRef]:
    refs: list[DepRef] = []
    for match in _TEMPLATE_REF_RE.finditer(template):
        full = match.group(0)
        name = match.group(1)
        kind: Literal["source", "ref"] = "source" if full.startswith("source") else "ref"
        refs.append(DepRef(kind=kind, name=name))
    return refs
