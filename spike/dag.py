"""Three-node DAG definition for the spike: map → reduce → single (§6, Phase 0)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

NodeKind = Literal["map", "reduce", "single"]


@dataclass(frozen=True)
class SpikeProject:
    root: Path
    model: str
    temperature: float
    max_tokens: int
    notes_glob: str
    spec_path: Path
    summarize_prompt: Path
    synthesize_prompt: Path
    polish_prompt: Path
    outputs_dir: Path


@dataclass(frozen=True)
class MapItem:
    path: str
    name: str
    stem: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    kind: NodeKind
    step: str
    prompt_path: Path
    item: MapItem | None = None


def default_project(root: Path) -> SpikeProject:
    return SpikeProject(
        root=root,
        model="ollama-cloud/kimi-k2.6:cloud",
        temperature=0.0,
        max_tokens=500,
        notes_glob="inputs/notes/*.md",
        spec_path=root / "inputs" / "spec.md",
        summarize_prompt=root / "prompts" / "summarize.md",
        synthesize_prompt=root / "prompts" / "synthesize.md",
        polish_prompt=root / "prompts" / "polish.md",
        outputs_dir=root / "outputs",
    )


def load_notes(project: SpikeProject) -> list[MapItem]:
    from spike.canonical import hash_bytes

    paths = sorted((project.root / "inputs" / "notes").glob("*.md"))
    items: list[MapItem] = []
    for path in paths:
        data = path.read_bytes()
        text = data.decode("utf-8")
        items.append(
            MapItem(
                path=str(path.relative_to(project.root)),
                name=path.name,
                stem=path.stem,
                content=text,
                content_hash=hash_bytes(data),
            )
        )
    return items
