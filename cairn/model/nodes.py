"""Built graph nodes (§8.2 DAG Builder output)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from cairn.model.project import Materialization, Prompt, SourceFile

NodeKind = Literal["map", "reduce", "single"]


@dataclass(frozen=True)
class Node:
    node_id: str
    step: str
    kind: NodeKind
    prompt: Prompt
    model: str
    params: dict[str, Any]
    materialization: Materialization
    output_path: str
    item: SourceFile | None
    input_digests: tuple[str, ...]
    declared_refs: tuple[str, ...]
    declared_sources: tuple[str, ...]
    system: str
    sample_index: int = 0

    @property
    def cache_kind(self) -> str:
        return "chat"
