"""Planner — pure function of (Project graph, CacheView) (§8.2, R1)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Protocol

from cairn.graph.builder import BuiltGraph
from cairn.loader.prompts import render_template
from cairn.loader.refs import parse_dep_expr
from cairn.loader.sources import resolve_source_files
from cairn.model.nodes import Node
from cairn.model.project import Project
from cairn.plan.action_key import action_key
from cairn.plan.cost import estimate_node_cost
from cairn.util.canonical import hash_bytes

NodeState = Literal["cached-hit", "stale", "new"]


class CacheView(Protocol):
    def get_output_hash(self, key: str) -> str | None: ...

    def has_blob(self, digest: str) -> bool: ...


@dataclass(frozen=True)
class PlannedNode:
    node: Node
    action_key: str
    state: NodeState
    output_hash: str | None
    estimated_cost: float | None
    cost_unpriced: bool
    rendered_prompt: str


@dataclass(frozen=True)
class Plan:
    nodes: tuple[PlannedNode, ...]
    total_estimated_cost: float
    has_unpriced: bool
    work_count: int


def _input_digests_for(
    project: Project,
    graph: BuiltGraph,
    node: Node,
    resolved_outputs: dict[str, str],
) -> tuple[str, ...] | None:
    if node.kind == "map" and node.item is not None:
        return (node.item.content_hash,)

    digests: list[str] = []
    step = project.steps[node.step]
    assert step.inputs is not None
    for expr in step.inputs:
        dep = parse_dep_expr(expr)
        if dep.kind == "source":
            for sf in resolve_source_files(project, dep.name):
                digests.append(sf.content_hash)
        else:
            for upstream in (n for n in graph.nodes if n.step == dep.name):
                digest = resolved_outputs.get(upstream.node_id)
                if digest is None:
                    return None
                digests.append(digest)
    return tuple(digests)


def _classify_state(node: Node, key: str, cache: CacheView) -> tuple[NodeState, str | None]:
    if node.materialization == "volatile":
        return "stale", cache.get_output_hash(key)
    existing = cache.get_output_hash(key)
    if existing is not None and cache.has_blob(existing):
        return "cached-hit", existing
    if existing is not None:
        return "stale", existing
    return "new", None


def _render_node_prompt(
    project: Project,
    graph: BuiltGraph,
    node: Node,
    output_texts: dict[str, str],
) -> str:
    if node.kind == "map" and node.item is not None:
        return render_template(
            node.prompt.template_body,
            {"item": node.item, **project.vars},
        )
    step = project.steps[node.step]
    assert step.inputs is not None
    context: dict[str, object] = dict(project.vars)
    for expr in step.inputs:
        dep = parse_dep_expr(expr)
        if dep.kind == "source":
            files = resolve_source_files(project, dep.name)
            if len(files) == 1:
                context[dep.name] = files[0].content
            else:
                context[dep.name] = [f.content for f in files]
        else:
            upstream = [n for n in graph.nodes if n.step == dep.name]
            if len(upstream) == 1:
                context[dep.name] = output_texts.get(upstream[0].node_id, "")
            else:
                context[dep.name] = [
                    {
                        "stem": n.item.stem if n.item else n.step,
                        "content": output_texts.get(n.node_id, ""),
                    }
                    for n in sorted(upstream, key=lambda n: n.node_id)
                ]
    return render_template(node.prompt.template_body, context)


def _plan_one(
    project: Project,
    graph: BuiltGraph,
    cache: CacheView,
    base: Node,
    *,
    resolved_hashes: dict[str, str],
    output_texts: dict[str, str],
) -> PlannedNode:
    digests = _input_digests_for(project, graph, base, resolved_hashes)
    if digests is None:
        node = replace(base, input_digests=())
        key = ""
        state: NodeState = "new"
        out_hash = None
    else:
        node = replace(base, input_digests=digests)
        key = action_key(node)
        state, out_hash = _classify_state(node, key, cache)
    rendered = _render_node_prompt(project, graph, node, output_texts)
    est = estimate_node_cost(node.model, rendered, node.params, project.prices)
    return PlannedNode(
        node=node,
        action_key=key,
        state=state,
        output_hash=out_hash,
        estimated_cost=est.cost,
        cost_unpriced=est.unpriced,
        rendered_prompt=rendered,
    )


def plan_nodes(
    project: Project,
    graph: BuiltGraph,
    cache: CacheView,
    node_ids: tuple[str, ...],
    *,
    seed_output_texts: dict[str, str] | None = None,
    seed_output_hashes: dict[str, str] | None = None,
) -> tuple[PlannedNode, ...]:
    """Plan only the given node ids — O(len(node_ids)) per call.

    The executor calls this once per dependency level, so total planning over a
    build is O(N) in the number of nodes, not O(N²).
    """
    resolved_hashes: dict[str, str] = dict(seed_output_hashes or {})
    if seed_output_texts and not seed_output_hashes:
        resolved_hashes.update(
            {nid: hash_bytes(text.encode("utf-8")) for nid, text in seed_output_texts.items()}
        )
    elif seed_output_texts:
        for nid, text in seed_output_texts.items():
            resolved_hashes.setdefault(nid, hash_bytes(text.encode("utf-8")))

    output_texts = dict(seed_output_texts or {})
    nodes_by_id = {n.node_id: n for n in graph.nodes}
    planned: list[PlannedNode] = []
    for node_id in node_ids:
        base = nodes_by_id[node_id]
        pn = _plan_one(
            project,
            graph,
            cache,
            base,
            resolved_hashes=resolved_hashes,
            output_texts=output_texts,
        )
        if pn.output_hash is not None:
            resolved_hashes[node_id] = pn.output_hash
        planned.append(pn)
    return tuple(planned)


def plan_build(
    project: Project,
    graph: BuiltGraph,
    cache: CacheView,
    *,
    seed_output_texts: dict[str, str] | None = None,
) -> Plan:
    """Compute action keys and classify all nodes. Pure w.r.t. cache view."""
    planned = plan_nodes(
        project,
        graph,
        cache,
        graph.topo_order,
        seed_output_texts=seed_output_texts,
    )
    total_cost = 0.0
    has_unpriced = False
    work_count = 0
    for pn in planned:
        if pn.cost_unpriced:
            has_unpriced = True
        if pn.state != "cached-hit":
            work_count += 1
            if pn.estimated_cost is not None:
                total_cost += pn.estimated_cost
    return Plan(
        nodes=planned,
        total_estimated_cost=total_cost,
        has_unpriced=has_unpriced,
        work_count=work_count,
    )
