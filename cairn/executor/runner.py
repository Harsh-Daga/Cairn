"""Async build executor (R12)."""

from __future__ import annotations

import asyncio
import fcntl
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cairn.cache.store import CacheStore
from cairn.executor.coalesce import RequestCoalescer
from cairn.graph.builder import BuiltGraph
from cairn.graph.levels import compute_node_levels
from cairn.ledger.ledger import Ledger, NodeStatus
from cairn.ledger.run_record import write_run_json
from cairn.model.messages import CompletionRequest, Message, TextBlock
from cairn.model.project import Project
from cairn.model.system import DEFAULT_SYSTEM_PROMPT
from cairn.plan.cost import actual_node_cost
from cairn.plan.planner import PlannedNode, plan_nodes
from cairn.providers.capabilities import infer_provider
from cairn.providers.protocol import Provider
from cairn.util.canonical import hash_bytes

# Executor calls plan_nodes once per dependency level → O(N) planning per build.


@dataclass
class BuildStats:
    hits: int = 0
    misses: int = 0
    tokens_spent: int = 0
    cost_spent: float = 0.0
    blocked_by_cost: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NodeBuildResult:
    node_id: str
    action_key: str
    output_hash: str
    output_text: str
    cache_hit: bool
    input_tokens: int
    output_tokens: int


@dataclass
class BuildResult:
    nodes: list[NodeBuildResult]
    stats: BuildStats
    dry_run: bool
    run_id: str | None = None


class _CachePlanView:
    def __init__(self, store: CacheStore) -> None:
        self._store = store

    def get_output_hash(self, key: str) -> str | None:
        return self._store.get_output_hash(key)

    def has_blob(self, digest: str) -> bool:
        return self._store.has_blob(digest)


@dataclass
class BuildOptions:
    dry_run: bool = False
    refresh_keys: frozenset[str] = frozenset()
    concurrency: int = 4
    max_cost: float | None = None
    yes: bool = False


def _completion_request(node: PlannedNode) -> CompletionRequest:
    provider = infer_provider(node.node.model)
    system = node.node.system or DEFAULT_SYSTEM_PROMPT
    return CompletionRequest(
        model=node.node.model,
        messages=(
            Message(role="system", content=(TextBlock(text=system),)),
            Message(role="user", content=(TextBlock(text=node.rendered_prompt),)),
        ),
        params=node.node.params,
        provider=provider,
    )


def _record_node(
    ledger: Ledger,
    run_id: str,
    planned: PlannedNode,
    result: NodeBuildResult,
    *,
    started_at: str,
    ended_at: str,
    duration_ms: int,
    project: Project,
) -> None:
    status: NodeStatus = "cached" if result.cache_hit else "ran"
    cost = actual_node_cost(
        planned.node.model,
        result.input_tokens,
        result.output_tokens,
        project.prices,
    )
    system = planned.node.system or DEFAULT_SYSTEM_PROMPT
    item_id = planned.node.item.path if planned.node.item else None
    ledger.record_node(
        run_id,
        node_id=planned.node.node_id,
        step=planned.node.step,
        item_id=item_id,
        kind=planned.node.kind,
        action_key=result.action_key,
        output_hash=result.output_hash,
        status=status,
        model=planned.node.model,
        params=planned.node.params,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost=cost,
        duration_ms=duration_ms,
        started_at=started_at,
        ended_at=ended_at,
        rendered_prompt=planned.rendered_prompt,
        system_prompt=system,
    )
    if result.output_hash:
        ledger.record_cas_ref(result.output_hash, run_id, planned.node.node_id)


async def execute_build(
    project: Project,
    graph: BuiltGraph,
    cache: CacheStore,
    provider: Provider,
    options: BuildOptions,
) -> BuildResult:
    for key in options.refresh_keys:
        cache.invalidate(key)

    stats = BuildStats()
    results_by_id: dict[str, NodeBuildResult] = {}
    output_texts: dict[str, str] = {}
    output_hashes: dict[str, str] = {}
    sem = asyncio.Semaphore(options.concurrency)
    coalescer: RequestCoalescer[NodeBuildResult] = RequestCoalescer()
    cost_lock = asyncio.Lock()
    reserved_cost = 0.0
    cache_view = _CachePlanView(cache)
    levels = compute_node_levels(project, graph)
    ledger = cache.ledger
    write_lock = asyncio.Lock()
    run_id: str | None = None
    record_ledger = not options.dry_run

    if record_ledger:
        run_id = ledger.begin_run(project.root)

    async def run_node(planned: PlannedNode) -> NodeBuildResult:
        started_mono = time.monotonic()
        started_at = datetime.now(UTC).isoformat()

        if (
            planned.state == "cached-hit"
            and planned.action_key not in options.refresh_keys
            and planned.output_hash
        ):
            blob = cache.read_blob(planned.output_hash)
            text = blob.decode("utf-8") if blob else ""
            stats.hits += 1
            result = NodeBuildResult(
                node_id=planned.node.node_id,
                action_key=planned.action_key,
                output_hash=planned.output_hash,
                output_text=text,
                cache_hit=True,
                input_tokens=0,
                output_tokens=0,
            )
            if record_ledger and run_id:
                ended_at = datetime.now(UTC).isoformat()
                duration_ms = int((time.monotonic() - started_mono) * 1000)
                async with write_lock:
                    _record_node(
                        ledger,
                        run_id,
                        planned,
                        result,
                        started_at=started_at,
                        ended_at=ended_at,
                        duration_ms=duration_ms,
                        project=project,
                    )
            return result

        if options.dry_run:
            stats.misses += 1
            placeholder = f"[dry-run:{planned.node.node_id}]"
            digest = hash_bytes(placeholder.encode("utf-8"))
            return NodeBuildResult(
                node_id=planned.node.node_id,
                action_key=planned.action_key,
                output_hash=digest,
                output_text=placeholder,
                cache_hit=False,
                input_tokens=0,
                output_tokens=0,
            )

        nonlocal reserved_cost
        est = planned.estimated_cost or 0.0
        if options.max_cost is not None and planned.estimated_cost is not None:
            async with cost_lock:
                if reserved_cost + planned.estimated_cost > options.max_cost:
                    stats.blocked_by_cost.append(planned.node.node_id)
                    msg = f"--max-cost exceeded before node {planned.node.node_id!r}"
                    raise RuntimeError(msg)
                reserved_cost += est

        async def _call() -> NodeBuildResult:
            req = _completion_request(planned)
            result = await provider.complete(req)
            stats.tokens_spent += result.usage.input_tokens + result.usage.output_tokens
            node_cost = actual_node_cost(
                planned.node.model,
                result.usage.input_tokens,
                result.usage.output_tokens,
                project.prices,
            )
            if node_cost is not None:
                stats.cost_spent += node_cost
            digest = cache.bind(
                planned.action_key,
                result.text.encode("utf-8"),
                kind=planned.node.cache_kind,
                model=planned.node.model,
            )
            return NodeBuildResult(
                node_id=planned.node.node_id,
                action_key=planned.action_key,
                output_hash=digest,
                output_text=result.text,
                cache_hit=False,
                input_tokens=result.usage.input_tokens,
                output_tokens=result.usage.output_tokens,
            )

        async with sem:
            built = await coalescer.run(planned.action_key, _call)
        stats.misses += 1
        if record_ledger and run_id:
            ended_at = datetime.now(UTC).isoformat()
            duration_ms = int((time.monotonic() - started_mono) * 1000)
            async with write_lock:
                _record_node(
                    ledger,
                    run_id,
                    planned,
                    built,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                    project=project,
                )
        return built

    final_status = "success"
    try:
        for level in levels:
            planned_level = plan_nodes(
                project,
                graph,
                cache_view,
                level,
                seed_output_texts=output_texts,
                seed_output_hashes=output_hashes,
            )
            level_results = await asyncio.gather(
                *(run_node(planned) for planned in planned_level)
            )
            for result in level_results:
                results_by_id[result.node_id] = result
                output_texts[result.node_id] = result.output_text
                output_hashes[result.node_id] = result.output_hash
                if not options.dry_run:
                    node = next(n for n in graph.nodes if n.node_id == result.node_id)
                    out_path = project.root / node.output_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_text(result.output_text, encoding="utf-8")
    except Exception:
        if record_ledger and run_id:
            ledger.finish_run(
                run_id,
                "failed",
                total_cost=stats.cost_spent or None,
                total_input_tokens=sum(n.input_tokens for n in results_by_id.values()),
                total_output_tokens=sum(n.output_tokens for n in results_by_id.values()),
            )
            write_run_json(project.root, ledger, run_id)
        raise

    if stats.blocked_by_cost:
        final_status = "partial"

    if record_ledger and run_id:
        total_in = sum(n.input_tokens for n in results_by_id.values())
        total_out = sum(n.output_tokens for n in results_by_id.values())
        ledger.finish_run(
            run_id,
            final_status,  # type: ignore[arg-type]
            total_cost=stats.cost_spent or None,
            total_input_tokens=total_in,
            total_output_tokens=total_out,
        )
        write_run_json(project.root, ledger, run_id)

    ordered = [results_by_id[nid] for nid in graph.topo_order if nid in results_by_id]
    return BuildResult(nodes=ordered, stats=stats, dry_run=options.dry_run, run_id=run_id)


def run_build_sync(
    project: Project,
    graph: BuiltGraph,
    cache: CacheStore,
    provider: Provider,
    options: BuildOptions,
) -> BuildResult:
    lock_path = project.root / ".cairn" / "lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock_file:
        if not options.dry_run:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            return asyncio.run(execute_build(project, graph, cache, provider, options))
        finally:
            if not options.dry_run:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
