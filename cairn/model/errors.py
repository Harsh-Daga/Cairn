"""Structured errors for Cairn (errors are values with context)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CairnError(Exception):
    """Base error with a human-readable message."""

    message: str

    def __str__(self) -> str:
        return self.message


@dataclass(frozen=True)
class ValidationError(CairnError):
    """Project validation failed."""


@dataclass(frozen=True)
class CycleError(ValidationError):
    """Dependency cycle detected in the DAG."""

    path: tuple[str, ...]


@dataclass(frozen=True)
class MissingRefError(ValidationError):
    """Reference to unknown step or source."""

    ref: str
    context: str


@dataclass(frozen=True)
class OutputCollisionError(ValidationError):
    """Two map items resolve to the same output path."""

    step: str
    path: str


@dataclass(frozen=True)
class UndeclaredRefError(ValidationError):
    """Template references source/ref not declared in inputs/over."""

    step: str
    prompt: str
    reference: str
    kind: str


def cycle_error(path: tuple[str, ...]) -> CycleError:
    return CycleError(
        message=f"dependency cycle: {' -> '.join(path)}",
        path=path,
    )


def missing_ref_error(ref: str, context: str) -> MissingRefError:
    return MissingRefError(
        message=f"unknown {context} reference {ref!r}",
        ref=ref,
        context=context,
    )


def output_collision_error(step: str, path: str, detail: str) -> OutputCollisionError:
    return OutputCollisionError(message=detail, step=step, path=path)


def undeclared_ref_error(step: str, prompt: str, reference: str, kind: str) -> UndeclaredRefError:
    return UndeclaredRefError(
        message=(
            f"step {step!r} prompt {prompt!r}: undeclared {kind}({reference!r}) "
            f"in template (declare in inputs/over)"
        ),
        step=step,
        prompt=prompt,
        reference=reference,
        kind=kind,
    )
