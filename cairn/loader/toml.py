"""cairn.toml parsing and Pydantic validation (§6, §20.3)."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from cairn.model.errors import ValidationError
from cairn.model.project import Project, SourceDef, StepDef


class ProjectSection(BaseModel):
    name: str
    version: str = "0.1.0"


class DefaultsSection(BaseModel):
    model: str = "gpt-4o-mini"
    system: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


class SourceSection(BaseModel):
    include: list[str]
    exclude: list[str] = Field(default_factory=list)


class StepSection(BaseModel):
    prompt: str
    output: str
    model: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    materialization: Literal["cached", "volatile", "ephemeral"] = "cached"
    samples: int = 1
    tags: list[str] = Field(default_factory=list)
    over: str | None = None
    inputs: list[str] | None = None
    system: str | None = None
    kind: Literal["chat"] = "chat"

    @model_validator(mode="after")
    def check_dependency_mode(self) -> StepSection:
        has_over = self.over is not None
        has_inputs = self.inputs is not None
        if has_over == has_inputs:
            msg = (
                "step must declare exactly one of 'over' or 'inputs' "
                f"(got over={self.over!r}, inputs={self.inputs!r})"
            )
            raise ValueError(msg)
        return self


class CairnToml(BaseModel):
    project: ProjectSection
    defaults: DefaultsSection = Field(default_factory=DefaultsSection)
    vars: dict[str, Any] = Field(default_factory=dict)
    sources: dict[str, SourceSection] = Field(default_factory=dict)
    steps: dict[str, StepSection] = Field(default_factory=dict)
    prices: dict[str, dict[str, Any]] = Field(default_factory=dict)

    @field_validator("steps")
    @classmethod
    def steps_non_empty(cls, value: dict[str, StepSection]) -> dict[str, StepSection]:
        if not value:
            msg = "at least one step is required"
            raise ValueError(msg)
        return value


def load_cairn_toml(path: Path) -> CairnToml:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return CairnToml.model_validate(data)


def load_project(root: Path) -> Project:
    toml_path = root / "cairn.toml"
    if not toml_path.is_file():
        raise ValidationError(f"missing cairn.toml at {toml_path}")
    try:
        parsed = load_cairn_toml(toml_path)
    except Exception as exc:
        raise ValidationError(f"invalid cairn.toml: {exc}") from exc

    sources = {
        name: SourceDef(
            name=name,
            include=tuple(section.include),
            exclude=tuple(section.exclude),
        )
        for name, section in parsed.sources.items()
    }
    steps: dict[str, StepDef] = {}
    for name, section in parsed.steps.items():
        steps[name] = StepDef(
            name=name,
            kind=section.kind,
            prompt=section.prompt,
            output=section.output,
            model=section.model,
            params=dict(section.params),
            materialization=section.materialization,
            samples=section.samples,
            tags=tuple(section.tags),
            over=section.over,
            inputs=tuple(section.inputs) if section.inputs is not None else None,
            system=section.system,
        )
    return Project(
        root=root.resolve(),
        name=parsed.project.name,
        version=parsed.project.version,
        defaults_model=parsed.defaults.model,
        defaults_system=parsed.defaults.system,
        defaults_params=dict(parsed.defaults.params),
        vars=dict(parsed.vars),
        sources=sources,
        steps=steps,
        prices=dict(parsed.prices),
    )
