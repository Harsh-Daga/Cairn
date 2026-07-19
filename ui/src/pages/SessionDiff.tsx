import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { useState } from "react";
import { fetchTraceDiff } from "@/lib/api";
import { formatCost, formatDuration, formatTokens } from "@/lib/format";
import { PageShell } from "@/components/common/PageShell";
import { Chip } from "@/components/common/Chip";
import type { TraceDiffChange, TraceDiffEvidence, TraceDiffResponse } from "@/lib/types";

const INITIAL_TURNS = 200;

function formatDelta(value: number, digits = 0): string {
  if (value > 0) return `+${value.toFixed(digits)}`;
  return value.toFixed(digits);
}

function evidencePath(evidence: TraceDiffEvidence): string {
  const span = evidence.span_id ? `?span=${encodeURIComponent(evidence.span_id)}` : "";
  return `/sessions/${encodeURIComponent(evidence.trace_id)}${span}`;
}

export function SessionDiffPage() {
  const [params] = useSearchParams();
  const [visibleTurns, setVisibleTurns] = useState(INITIAL_TURNS);
  const traceIdA = params.get("a");
  const traceIdB = params.get("b");

  const { data, isLoading, isError } = useQuery({
    queryKey: ["trace-diff", traceIdA, traceIdB],
    queryFn: () => fetchTraceDiff(traceIdA!, traceIdB!),
    enabled: Boolean(traceIdA && traceIdB),
  });

  if (!traceIdA || !traceIdB) {
    return (
      <PageShell
        title="Session diff"
        question="Compare two runs turn by turn to explain changes in cost, waste, and quality."
      >
        <div className="card p-6 text-cinnabar">
          Select two sessions first from the Sessions page.
        </div>
      </PageShell>
    );
  }

  if (isLoading) {
    return (
      <PageShell
        title="Session diff"
        question="Compare two runs turn by turn to explain changes in cost, waste, and quality."
      >
        <div className="card h-64 animate-pulse bg-granite/30" />
      </PageShell>
    );
  }

  if (isError || !data) {
    return (
      <PageShell
        title="Session diff"
        question="Compare two runs turn by turn to explain changes in cost, waste, and quality."
      >
        <div className="card p-6 text-cinnabar">Failed to load diff payload.</div>
      </PageShell>
    );
  }

  const { analysis } = data;
  const shownTurns = data.turns.slice(0, visibleTurns);
  const maxTurnTokens = Math.max(
    1,
    ...shownTurns.flatMap((turn) => [
      (turn.a?.input_tokens ?? 0) + (turn.a?.output_tokens ?? 0),
      (turn.b?.input_tokens ?? 0) + (turn.b?.output_tokens ?? 0),
    ]),
  );

  return (
    <PageShell
      title="Session diff"
      question="Compare two runs turn by turn to explain changes in cost, waste, and quality."
    >
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Link to="/sessions" className="font-mono text-xs text-copper hover:underline">
          ← Sessions
        </Link>
        <Link
          to={`/sessions/${encodeURIComponent(data.a.trace_id)}`}
          className="font-mono text-[11px] text-copper"
        >
          A: {data.a.trace_id}
        </Link>
        <Link
          to={`/sessions/${encodeURIComponent(data.b.trace_id)}`}
          className="font-mono text-[11px] text-copper"
        >
          B: {data.b.trace_id}
        </Link>
      </div>

      <Comparability analysis={analysis} />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric
          label="Cost"
          before={formatCost(data.summary.cost_a, 4)}
          after={formatCost(data.summary.cost_b, 4)}
          delta={formatDelta(data.summary.delta_cost, 4)}
        />
        <Metric
          label="Tokens"
          before={formatTokens(analysis.tokens_a)}
          after={formatTokens(analysis.tokens_b)}
          delta={formatDelta(analysis.delta_tokens)}
        />
        <Metric
          label="Waste"
          before={formatTokens(data.summary.waste_a)}
          after={formatTokens(data.summary.waste_b)}
          delta={formatDelta(data.summary.delta_waste_tokens)}
        />
        <Metric
          label="Quality"
          before={`${(data.summary.quality_a * 100).toFixed(0)}%`}
          after={`${(data.summary.quality_b * 100).toFixed(0)}%`}
          delta={`${formatDelta(data.summary.delta_quality * 100, 1)} pts`}
        />
        <Metric
          label="Duration"
          before={formatDuration(analysis.duration_ms_a)}
          after={formatDuration(analysis.duration_ms_b)}
          delta={
            analysis.delta_duration_ms == null
              ? "unavailable"
              : formatDelta(analysis.delta_duration_ms) + " ms"
          }
        />
      </div>

      <div className="mb-4 grid gap-4 lg:grid-cols-2">
        <RecordedDifferences data={data} />
        <WhatChanged changes={analysis.what_changed} />
      </div>

      <RegionComposition data={data} />

      <section className="card mt-4 overflow-hidden" aria-label="Aligned session timeline">
        <div className="border-b border-quartz-vein px-4 py-3">
          <h2 className="font-display text-base text-bone">Aligned timeline / waterfall summary</h2>
          <p className="mt-1 text-xs text-cinder">
            Alignment is descriptive over recorded span kind and name. Insertions and deletions are
            not proof of a regression or improvement.
          </p>
          {analysis.alignment_limitation ? (
            <p className="mt-2 text-xs text-ochre">{analysis.alignment_limitation}</p>
          ) : null}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead className="border-b border-quartz-vein bg-slate font-mono text-[10px] uppercase tracking-wide text-cinder">
              <tr>
                <th className="px-3 py-2">#</th>
                <th className="px-3 py-2">Aligned spans</th>
                <th className="px-3 py-2 text-right">Δ tokens</th>
                <th className="px-3 py-2 text-right">Δ waste</th>
                <th className="px-3 py-2 text-right">Δ quality</th>
                <th className="px-3 py-2">Evidence</th>
              </tr>
            </thead>
            <tbody>
              {shownTurns.map((turn) => {
                const labelA = turn.a ? `${turn.a.kind}:${turn.a.name ?? "(unnamed)"}` : "—";
                const labelB = turn.b ? `${turn.b.kind}:${turn.b.name ?? "(unnamed)"}` : "—";
                const tokensA = (turn.a?.input_tokens ?? 0) + (turn.a?.output_tokens ?? 0);
                const tokensB = (turn.b?.input_tokens ?? 0) + (turn.b?.output_tokens ?? 0);
                return (
                  <tr key={`${turn.index}-${turn.op}`} className="border-b border-quartz-vein/50">
                    <td className="px-3 py-2 font-mono text-xs text-cinder">{turn.index}</td>
                    <td className="w-[45%] px-3 py-2">
                      <div className="font-mono text-[10px] uppercase text-cinder">{turn.op}</div>
                      <TimelineBar label={`A · ${labelA}`} tokens={tokensA} max={maxTurnTokens} />
                      <TimelineBar label={`B · ${labelB}`} tokens={tokensB} max={maxTurnTokens} />
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      {formatDelta(turn.delta_tokens)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      {formatDelta(turn.delta_waste_tokens)}
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs">
                      {formatDelta(turn.delta_quality, 2)}
                    </td>
                    <td className="px-3 py-2 font-mono text-[10px]">
                      {turn.a ? (
                        <Link
                          to={`/sessions/${encodeURIComponent(data.a.trace_id)}?span=${encodeURIComponent(turn.a.span_id)}`}
                          className="mr-2 text-copper"
                        >
                          A
                        </Link>
                      ) : null}
                      {turn.b ? (
                        <Link
                          to={`/sessions/${encodeURIComponent(data.b.trace_id)}?span=${encodeURIComponent(turn.b.span_id)}`}
                          className="text-copper"
                        >
                          B
                        </Link>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {visibleTurns < data.turns.length ? (
          <div className="border-t border-quartz-vein p-3 text-center">
            <button
              type="button"
              className="rounded-sm border border-quartz-vein px-4 py-2 font-mono text-xs text-copper"
              onClick={() => setVisibleTurns((value) => value + INITIAL_TURNS)}
            >
              Show next {Math.min(INITIAL_TURNS, data.turns.length - visibleTurns)} aligned rows
            </button>
          </div>
        ) : null}
      </section>
    </PageShell>
  );
}

function Comparability({ analysis }: { analysis: TraceDiffResponse["analysis"] }) {
  const { comparability } = analysis;
  return (
    <section
      className={`mb-4 card border-l-4 p-4 ${
        comparability.state === "comparable"
          ? "border-l-malachite"
          : comparability.state === "limited"
            ? "border-l-ochre"
            : "border-l-cinnabar"
      }`}
      aria-label="Comparison validity"
    >
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-display text-base text-bone">Comparison validity</h2>
        <Chip
          label={comparability.state.replace("_", " ")}
          tone={comparability.state === "comparable" ? "patina" : "cinnabar"}
        />
        <Chip label={analysis.alignment_mode.replace("_", " ")} tone="estimated" />
      </div>
      {comparability.facts.length > 0 ? (
        <ul className="mt-2 text-xs text-bone">
          {comparability.facts.map((fact) => (
            <li key={fact}>• {fact}</li>
          ))}
        </ul>
      ) : null}
      {comparability.reasons.length > 0 ? (
        <ul className="mt-2 text-xs text-ochre">
          {comparability.reasons.map((reason) => (
            <li key={reason}>• {reason}</li>
          ))}
        </ul>
      ) : null}
      <p className="mt-2 text-xs text-cinder">{comparability.limitation}</p>
    </section>
  );
}

function Metric({
  label,
  before,
  after,
  delta,
}: {
  label: string;
  before: string;
  after: string;
  delta: string;
}) {
  return (
    <div className="card p-3">
      <div className="font-mono text-[10px] uppercase tracking-wide text-cinder">{label} delta</div>
      <div className="mt-1 text-sm text-bone">
        {before} → {after}
      </div>
      <div className="font-mono text-xs text-copper">{delta}</div>
    </div>
  );
}

function RecordedDifferences({ data }: { data: TraceDiffResponse }) {
  const { analysis } = data;
  return (
    <section className="card p-4" aria-label="Recorded model and outcome differences">
      <h2 className="font-display text-base text-bone">Models, outcomes, and diagnoses</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 text-xs">
        <SideFact
          side="A"
          model={analysis.models_a.join(", ") || "unavailable"}
          outcome={analysis.outcome_a?.outcome_label ?? "unavailable"}
          diagnose={analysis.diagnostic_a?.primary_category ?? "unavailable"}
        />
        <SideFact
          side="B"
          model={analysis.models_b.join(", ") || "unavailable"}
          outcome={analysis.outcome_b?.outcome_label ?? "unavailable"}
          diagnose={analysis.diagnostic_b?.primary_category ?? "unavailable"}
        />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        {analysis.evidence.map((evidence) => (
          <Link
            key={`${evidence.side}-${evidence.trace_id}-${evidence.span_id ?? ""}-${evidence.label}`}
            to={evidencePath(evidence)}
            className="rounded-sm border border-quartz-vein px-2 py-1 font-mono text-[10px] text-copper"
          >
            {evidence.label}
          </Link>
        ))}
      </div>
    </section>
  );
}

function SideFact({
  side,
  model,
  outcome,
  diagnose,
}: {
  side: string;
  model: string;
  outcome: string;
  diagnose: string;
}) {
  return (
    <dl className="rounded-sm border border-quartz-vein p-3">
      <dt className="font-mono text-[10px] text-cinder">Session {side}</dt>
      <dd className="mt-2 text-bone">Models: {model}</dd>
      <dd className="mt-1 text-bone">Outcome: {outcome}</dd>
      <dd className="mt-1 text-bone">Diagnose: {diagnose}</dd>
    </dl>
  );
}

function WhatChanged({ changes }: { changes: TraceDiffChange[] }) {
  return (
    <section className="card p-4" aria-label="What changed">
      <h2 className="font-display text-base text-bone">What changed</h2>
      <p className="mt-1 text-xs text-cinder">
        Deterministic summaries of recorded deltas and diagnose fields; no causal attribution.
      </p>
      <ol className="mt-3 space-y-3">
        {changes.map((change, index) => (
          <li key={`${change.basis}-${index}`} className="rounded-sm border border-quartz-vein p-3">
            <Chip label={change.basis.replace("_", " ")} tone="estimated" />
            <p className="mt-2 text-xs text-bone">{change.statement}</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {change.evidence.map((evidence) => (
                <Link
                  key={`${evidence.trace_id}-${evidence.span_id ?? ""}-${evidence.label}`}
                  to={evidencePath(evidence)}
                  className="font-mono text-[10px] text-copper"
                >
                  {evidence.side.toUpperCase()} evidence
                </Link>
              ))}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

function RegionComposition({ data }: { data: TraceDiffResponse }) {
  return (
    <section className="card overflow-hidden" aria-label="Region composition difference">
      <div className="border-b border-quartz-vein px-4 py-3">
        <h2 className="font-display text-base text-bone">Context-region composition</h2>
        <p className="mt-1 text-xs text-cinder">
          Only measured/estimated region rows captured for these sessions are included.
        </p>
      </div>
      {data.analysis.regions.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-sm">
            <thead className="bg-slate font-mono text-[10px] uppercase text-cinder">
              <tr>
                <th className="px-3 py-2 text-left">Region</th>
                <th className="px-3 py-2 text-right">A tokens</th>
                <th className="px-3 py-2 text-right">B tokens</th>
                <th className="px-3 py-2 text-right">Δ tokens</th>
                <th className="px-3 py-2 text-right">Δ cost</th>
              </tr>
            </thead>
            <tbody>
              {data.analysis.regions.map((region) => (
                <tr key={region.region} className="border-t border-quartz-vein/50">
                  <td className="px-3 py-2 text-bone">{region.region}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatTokens(region.tokens_a)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatTokens(region.tokens_b)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatDelta(region.delta_tokens)}
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs">
                    {formatDelta(region.delta_cost, 4)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-4 text-sm text-cinder">
          Region composition was not captured for either session.
        </p>
      )}
    </section>
  );
}

function TimelineBar({ label, tokens, max }: { label: string; tokens: number; max: number }) {
  const width = tokens > 0 ? Math.max(2, (tokens / max) * 100) : 0;
  return (
    <div className="mt-1 grid grid-cols-[minmax(140px,1fr)_35%] items-center gap-2">
      <span className="truncate text-xs text-bone">{label}</span>
      <span className="h-2 rounded-sm bg-granite/50">
        <span
          className="block h-full rounded-sm bg-copper/60"
          style={{ width: `${width}%` }}
          aria-label={`${tokens} tokens`}
        />
      </span>
    </div>
  );
}
