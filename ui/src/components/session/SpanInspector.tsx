import { useState } from "react";
import type { ContextRegion, Span, SpanLink } from "@/lib/types";
import { Chip } from "@/components/common/Chip";
import { formatDuration, formatTokens } from "@/lib/format";

type InspectorTab = "summary" | "content" | "context" | "links";

interface SpanInspectorProps {
  span: Span | null;
  regions?: ContextRegion[];
  links?: SpanLink[];
  onSelectSpan?: (spanId: string) => void;
}

export function SpanInspector({
  span,
  regions = [],
  links = [],
  onSelectSpan,
}: SpanInspectorProps) {
  const [tab, setTab] = useState<InspectorTab>("summary");

  if (!span) {
    return (
      <aside className="card flex h-full items-center justify-center p-4 text-sm text-cinder">
        Select a span to inspect
      </aside>
    );
  }

  const estimated = span.input_estimated > 0 || span.output_estimated > 0;
  const hasWaste = span.waste_tokens > 0 || span.waste_category != null;
  const spanRegions = regions.filter((region) => region.span_id === span.span_id);
  const spanLinks = links.filter(
    (link) => link.from_span_id === span.span_id || link.to_span_id === span.span_id,
  );

  return (
    <aside className="card flex h-full flex-col overflow-hidden" aria-label="Span inspector">
      <div className="flex border-b border-quartz-vein" role="tablist" aria-label="Inspector views">
        {(["summary", "content", "context", "links"] as const).map((nextTab) => (
          <button
            key={nextTab}
            type="button"
            role="tab"
            aria-selected={tab === nextTab}
            className={`flex-1 px-2 py-2 font-mono text-[9px] uppercase tracking-wide ${
              tab === nextTab ? "border-b-2 border-copper text-bone" : "text-cinder hover:text-bone"
            }`}
            onClick={() => setTab(nextTab)}
          >
            {nextTab}
          </button>
        ))}
      </div>
      <div className="flex-1 overflow-auto p-4">
        {tab === "summary" ? (
          <>
            <div className="flex flex-wrap gap-2">
              <Chip label={span.kind} tone="patina" />
              {span.status === "error" ? <Chip label="error" tone="cinnabar" /> : null}
              {estimated ? <Chip label="est." tone="estimated" /> : null}
              {span.waste_category ? <Chip label={span.waste_category} tone="ochre" /> : null}
            </div>
            <h3 className="mt-3 font-mono text-sm text-bone">{span.name ?? span.kind}</h3>
            <dl className="mt-4 space-y-2 font-mono text-[11px]">
              <Fact label="seq" value={String(span.seq)} />
              <Fact
                label="tokens in/out"
                value={`${formatTokens(span.input_tokens ?? 0)} / ${formatTokens(
                  span.output_tokens ?? 0,
                )}`}
                estimated={estimated}
              />
              <Fact label="duration" value={formatDuration(span.duration_ms)} />
              {span.context_tokens_after != null ? (
                <Fact label="context after" value={formatTokens(span.context_tokens_after)} />
              ) : null}
              {span.path_rel ? <Fact label="path" value={span.path_rel} /> : null}
            </dl>
            {hasWaste ? (
              <div className="mt-4 rounded-sm border border-ochre/40 p-3 text-xs text-cinder">
                {span.waste_category ?? "Recorded waste"} · {formatTokens(span.waste_tokens)}{" "}
                tokens. Waste attribution is recorded analysis, not a causal guarantee.
              </div>
            ) : null}
          </>
        ) : null}
        {tab === "content" ? (
          span.text_inline ? (
            <pre className="max-h-full overflow-auto whitespace-pre-wrap rounded-sm bg-granite/40 p-3 font-mono text-[10px] text-bone">
              {span.text_inline.slice(0, 4000)}
            </pre>
          ) : (
            <p className="text-sm text-cinder">No inline text for this span.</p>
          )
        ) : null}
        {tab === "context" ? (
          spanRegions.length > 0 ? (
            <dl className="space-y-3 font-mono text-[11px]">
              {spanRegions.map((region) => (
                <div
                  key={`${region.span_id}-${region.region}`}
                  className="rounded-sm border border-quartz-vein p-3"
                >
                  <dt className="text-cinder">{region.region}</dt>
                  <dd className="mt-1 text-bone">
                    {formatTokens(region.tokens)} tokens ·{" "}
                    {region.still_in_window ? "retained" : "left window"}
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="text-sm text-cinder">No context-region evidence for this span.</p>
          )
        ) : null}
        {tab === "links" ? (
          spanLinks.length > 0 ? (
            <ul className="space-y-2">
              {spanLinks.map((link) => {
                const target =
                  link.from_span_id === span.span_id ? link.to_span_id : link.from_span_id;
                return (
                  <li key={`${link.from_span_id}-${link.to_span_id}-${link.link_type}`}>
                    <button
                      type="button"
                      className="w-full rounded-sm border border-quartz-vein p-3 text-left font-mono text-[10px] text-copper"
                      onClick={() => onSelectSpan?.(target)}
                    >
                      {link.link_type} → {target}
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="text-sm text-cinder">No parent, retry, or handoff links were recorded.</p>
          )
        ) : null}
      </div>
    </aside>
  );
}

function Fact({
  label,
  value,
  estimated = false,
}: {
  label: string;
  value: string;
  estimated?: boolean;
}) {
  return (
    <div className="flex justify-between gap-4">
      <dt className="text-cinder">{label}</dt>
      <dd className={`truncate text-right ${estimated ? "estimated-chip" : ""}`}>{value}</dd>
    </div>
  );
}
