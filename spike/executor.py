"""Spike executor — topological build with content-addressed caching (§9, §11)."""

from __future__ import annotations

from dataclasses import dataclass

from spike.cache import CacheStats, SpikeCache
from spike.canonical import hash_bytes
from spike.dag import NodeSpec, SpikeProject, load_notes
from spike.keys import ActionKeyInput, PromptRef, action_key
from spike.prompts import load_prompt, prompt_body, render_prompt
from spike.provider import CompletionRequest, Provider


@dataclass(frozen=True)
class NodeResult:
    node_id: str
    step: str
    action_key: str
    output_hash: str
    output_text: str
    cache_hit: bool
    input_tokens: int
    output_tokens: int


@dataclass
class BuildReport:
    results: list[NodeResult]
    stats: CacheStats


def _params(project: SpikeProject) -> dict[str, float | int]:
    return {"max_tokens": project.max_tokens}


def _node_key(
    *,
    kind: str,
    prompt: PromptRef,
    project: SpikeProject,
    input_digests: tuple[str, ...],
) -> str:
    return action_key(
        ActionKeyInput(
            kind="chat",
            prompt=prompt,
            model=project.model,
            params=_params(project),
            input_digests=input_digests,
        )
    )


def _complete(
    provider: Provider,
    project: SpikeProject,
    system_and_user: tuple[str, str],
    stats: CacheStats,
) -> tuple[str, int, int]:
    system, user = system_and_user
    result = provider.complete(
        CompletionRequest(
            model=project.model,
            system=system,
            user=user,
            temperature=project.temperature,
            max_tokens=project.max_tokens,
        )
    )
    stats.tokens_spent += result.input_tokens + result.output_tokens
    return result.text, result.input_tokens, result.output_tokens


def _resolve_or_run(
    *,
    cache: SpikeCache,
    provider: Provider,
    project: SpikeProject,
    node: NodeSpec,
    prompt: PromptRef,
    user_message: str,
    input_digests: tuple[str, ...],
    stats: CacheStats,
    dry_run: bool,
) -> NodeResult:
    key = _node_key(
        kind=node.kind,
        prompt=prompt,
        project=project,
        input_digests=input_digests,
    )
    existing = cache.get_output_hash(key)
    if existing is not None:
        blob = cache.read_blob(existing)
        if blob is not None:
            stats.hits += 1
            return NodeResult(
                node_id=node.node_id,
                step=node.step,
                action_key=key,
                output_hash=existing,
                output_text=blob.decode("utf-8"),
                cache_hit=True,
                input_tokens=0,
                output_tokens=0,
            )

    stats.misses += 1
    if dry_run:
        placeholder = f"[dry-run:{node.node_id}]"
        output_hash = hash_bytes(placeholder.encode("utf-8"))
        return NodeResult(
            node_id=node.node_id,
            step=node.step,
            action_key=key,
            output_hash=output_hash,
            output_text=placeholder,
            cache_hit=False,
            input_tokens=0,
            output_tokens=0,
        )

    system = "Follow the user instructions precisely."
    text, in_tok, out_tok = _complete(provider, project, (system, user_message), stats)
    output_hash = cache.put_blob(text.encode("utf-8"))
    cache.bind(key, output_hash)
    return NodeResult(
        node_id=node.node_id,
        step=node.step,
        action_key=key,
        output_hash=output_hash,
        output_text=text,
        cache_hit=False,
        input_tokens=in_tok,
        output_tokens=out_tok,
    )


def build(
    project: SpikeProject,
    cache: SpikeCache,
    provider: Provider,
    *,
    dry_run: bool = False,
) -> BuildReport:
    """Execute map → reduce → single with caching."""
    stats = CacheStats()
    results: list[NodeResult] = []
    project.outputs_dir.mkdir(parents=True, exist_ok=True)
    (project.outputs_dir / "summaries").mkdir(parents=True, exist_ok=True)

    summarize = load_prompt(project.summarize_prompt)
    synthesize = load_prompt(project.synthesize_prompt)
    polish = load_prompt(project.polish_prompt)
    spec_hash = hash_bytes(project.spec_path.read_bytes())

    summary_outputs: dict[str, NodeResult] = {}

    # MAP: one summary per note
    for item in load_notes(project):
        node = NodeSpec(
            node_id=f"summaries:{item.stem}",
            kind="map",
            step="summaries",
            prompt_path=project.summarize_prompt,
            item=item,
        )
        map_user = render_prompt(prompt_body(summarize), {"item": item})
        result = _resolve_or_run(
            cache=cache,
            provider=provider,
            project=project,
            node=node,
            prompt=summarize,
            user_message=map_user,
            input_digests=(item.content_hash,),
            stats=stats,
            dry_run=dry_run,
        )
        results.append(result)
        summary_outputs[item.stem] = result
        out_path = project.outputs_dir / "summaries" / f"{item.stem}.md"
        if not dry_run:
            out_path.write_text(result.output_text, encoding="utf-8")

    # REDUCE: synthesis over summaries + spec
    synth_context = {
        "summaries": [
            {"stem": stem, "content": res.output_text}
            for stem, res in sorted(summary_outputs.items())
        ],
        "spec": project.spec_path.read_text(encoding="utf-8"),
    }
    synth_rendered = render_prompt(prompt_body(synthesize), synth_context)
    synth_digests = tuple(
        sorted([spec_hash, *[res.output_hash for res in summary_outputs.values()]])
    )
    synth_node = NodeSpec(
        node_id="synthesis",
        kind="reduce",
        step="synthesis",
        prompt_path=project.synthesize_prompt,
    )
    synth_result = _resolve_or_run(
        cache=cache,
        provider=provider,
        project=project,
        node=synth_node,
        prompt=synthesize,
        user_message=synth_rendered,
        input_digests=synth_digests,
        stats=stats,
        dry_run=dry_run,
    )
    results.append(synth_result)
    if not dry_run:
        synthesis_path = project.outputs_dir / "synthesis.md"
        synthesis_path.write_text(synth_result.output_text, encoding="utf-8")

    # SINGLE: polish the synthesis
    polish_context = {"synthesis": synth_result.output_text}
    polish_rendered = render_prompt(prompt_body(polish), polish_context)
    polish_node = NodeSpec(
        node_id="report",
        kind="single",
        step="report",
        prompt_path=project.polish_prompt,
    )
    polish_result = _resolve_or_run(
        cache=cache,
        provider=provider,
        project=project,
        node=polish_node,
        prompt=polish,
        user_message=polish_rendered,
        input_digests=(synth_result.output_hash,),
        stats=stats,
        dry_run=dry_run,
    )
    results.append(polish_result)
    if not dry_run:
        (project.outputs_dir / "report.md").write_text(polish_result.output_text, encoding="utf-8")

    return BuildReport(results=results, stats=stats)


def nodes_that_would_run(report: BuildReport) -> list[str]:
    return [r.node_id for r in report.results if not r.cache_hit]
