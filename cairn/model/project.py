"""Domain model: Project, Source, Prompt, Step (§5, §6, §20.3)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Materialization = Literal["cached", "volatile", "ephemeral"]
StepKind = Literal["chat"]


@dataclass(frozen=True)
class SourceDef:
    name: str
    include: tuple[str, ...]
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class StepDef:
    name: str
    kind: StepKind
    prompt: str
    output: str
    model: str | None
    params: dict[str, Any]
    materialization: Materialization
    samples: int
    tags: tuple[str, ...]
    over: str | None
    inputs: tuple[str, ...] | None
    system: str | None


@dataclass(frozen=True)
class Prompt:
    path: str
    template_body: str
    template_body_bytes: bytes
    front_matter: dict[str, Any]
    model_override: str | None
    params_override: dict[str, Any]


@dataclass(frozen=True)
class SourceFile:
    path: str
    name: str
    stem: str
    content: str
    content_hash: str


@dataclass(frozen=True)
class Project:
    root: Path
    name: str
    version: str
    defaults_model: str
    defaults_system: str | None
    defaults_params: dict[str, Any]
    vars: dict[str, Any]
    sources: dict[str, SourceDef]
    steps: dict[str, StepDef]
    prices: dict[str, dict[str, Any]] = field(default_factory=dict)
