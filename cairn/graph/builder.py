"""DAG builder — resolve over/inputs/ref()/source() into a node graph (§8.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cairn.loader.prompts import load_prompt, render_template
from cairn.loader.refs import DepRef, find_template_refs, parse_dep_expr
from cairn.loader.sources import resolve_source_files
from cairn.model.errors import (
    ValidationError,
    cycle_error,
    missing_ref_error,
    output_collision_error,
    undeclared_ref_error,
)
from cairn.model.nodes import Node, NodeKind
from cairn.model.project import Project, SourceFile, StepDef
from cairn.model.system import DEFAULT_SYSTEM_PROMPT


@dataclass(frozen=True)
class BuiltGraph:
    nodes: tuple[Node, ...]
    topo_order: tuple[str, ...]


def _merge_params(
    project: Project,
    step: StepDef,
    prompt_params: dict[str, object],
) -> dict[str, object]:
    merged: dict[str, object] = dict(project.defaults_params)
    merged.update(step.params)
    merged.update(prompt_params)
    return merged


def _resolve_model(project: Project, step: StepDef, prompt_model: str | None) -> str:
    if prompt_model is not None:
        return prompt_model
    if step.model is not None:
        return step.model
    return project.defaults_model


def _resolve_system(project: Project, step: StepDef) -> str:
    if step.system is not None:
        return step.system
    if project.defaults_system is not None:
        return project.defaults_system
    return DEFAULT_SYSTEM_PROMPT


def _step_deps(step: StepDef) -> tuple[DepRef, ...]:
    if step.over is not None:
        return (parse_dep_expr(step.over),)
    assert step.inputs is not None
    return tuple(parse_dep_expr(expr) for expr in step.inputs)


def _validate_template_refs(step: StepDef, prompt_path: Path, project: Project) -> None:
    prompt = load_prompt(prompt_path, project.root)
    declared_sources = {d.name for d in _step_deps(step) if d.kind == "source"}
    declared_refs = {d.name for d in _step_deps(step) if d.kind == "ref"}
    for ref in find_template_refs(prompt.template_body):
        if ref.kind == "source" and ref.name not in declared_sources:
            raise undeclared_ref_error(step.name, prompt.path, ref.name, "source")
        if ref.kind == "ref" and ref.name not in declared_refs:
            raise undeclared_ref_error(step.name, prompt.path, ref.name, "ref")


def _detect_cycles(graph: dict[str, set[str]]) -> None:
    visited: set[str] = set()
    stack: set[str] = set()
    path: list[str] = []

    def visit(node: str) -> None:
        if node in stack:
            cycle_start = path.index(node)
            raise cycle_error(tuple(path[cycle_start:] + [node]))
        if node in visited:
            return
        visited.add(node)
        stack.add(node)
        path.append(node)
        for dep in graph.get(node, set()):
            visit(dep)
        path.pop()
        stack.remove(node)

    for step_name in graph:
        if step_name not in visited:
            visit(step_name)


def _render_output_path(project: Project, template: str, item: SourceFile | None) -> str:
    if item is None:
        return render_template(template, dict(project.vars))
    return render_template(template, {"item": item, **project.vars})


def build_graph(project: Project) -> BuiltGraph:
    """Build the node graph and validate dependencies."""
    adjacency: dict[str, set[str]] = {name: set() for name in project.steps}

    for name, step in project.steps.items():
        prompt_path = project.root / step.prompt
        if not prompt_path.is_file():
            raise ValidationError(f"step {name!r}: missing prompt {step.prompt}")
        _validate_template_refs(step, prompt_path, project)
        for dep in _step_deps(step):
            if dep.kind == "source":
                if dep.name not in project.sources:
                    raise missing_ref_error(dep.name, f"source in step {name!r}")
            elif dep.name not in project.steps:
                raise missing_ref_error(dep.name, f"ref in step {name!r}")
            else:
                adjacency[name].add(dep.name)

    _detect_cycles(adjacency)

    nodes: list[Node] = []
    output_paths_seen: dict[str, str] = {}

    for step_name, step in project.steps.items():
        prompt = load_prompt(project.root / step.prompt, project.root)
        model = _resolve_model(project, step, prompt.model_override)
        params = _merge_params(project, step, prompt.params_override)
        system = _resolve_system(project, step)

        if step.over is not None:
            dep = parse_dep_expr(step.over)
            if dep.kind == "source":
                items = resolve_source_files(project, dep.name)
                for item in items:
                    out_path = _render_output_path(project, step.output, item)
                    if out_path in output_paths_seen:
                        raise output_collision_error(
                            step_name,
                            out_path,
                            (
                                f"output path collision in step {step_name!r}: {out_path!r} "
                                f"(also from {output_paths_seen[out_path]!r})"
                            ),
                        )
                    output_paths_seen[out_path] = f"{step_name}:{item.stem}"
                    node_id = f"{step_name}:{item.stem}"
                    nodes.append(
                        Node(
                            node_id=node_id,
                            step=step_name,
                            kind="map",
                            prompt=prompt,
                            model=model,
                            params=params,
                            materialization=step.materialization,
                            output_path=out_path,
                            item=item,
                            input_digests=(item.content_hash,),
                            declared_refs=(),
                            declared_sources=(dep.name,),
                            system=system,
                        )
                    )
            else:
                msg = "map over ref() is Phase 4+; use source() in Phase 1"
                raise ValidationError(msg)
        else:
            assert step.inputs is not None
            declared_sources = tuple(
                d.name for d in (parse_dep_expr(e) for e in step.inputs) if d.kind == "source"
            )
            declared_refs = tuple(
                d.name for d in (parse_dep_expr(e) for e in step.inputs) if d.kind == "ref"
            )
            kind: NodeKind = "reduce" if len(step.inputs) > 1 else "single"
            out_path = _render_output_path(project, step.output, None)
            if out_path in output_paths_seen:
                raise output_collision_error(
                    step_name,
                    out_path,
                    f"output path collision: {out_path!r}",
                )
            output_paths_seen[out_path] = step_name
            nodes.append(
                Node(
                    node_id=step_name,
                    step=step_name,
                    kind=kind,
                    prompt=prompt,
                    model=model,
                    params=params,
                    materialization=step.materialization,
                    output_path=out_path,
                    item=None,
                    input_digests=(),  # filled at plan time when upstream hashes known
                    declared_refs=declared_refs,
                    declared_sources=declared_sources,
                    system=system,
                )
            )

    topo: list[str] = []
    seen_steps: set[str] = set()

    def visit_step(step_name: str) -> None:
        if step_name in seen_steps:
            return
        for dep in adjacency.get(step_name, set()):
            visit_step(dep)
        seen_steps.add(step_name)
        topo.append(step_name)

    for step_name in project.steps:
        visit_step(step_name)

    node_order = tuple(
        n.node_id
        for step_name in topo
        for n in nodes
        if n.step == step_name
    )
    return BuiltGraph(nodes=tuple(nodes), topo_order=node_order)
