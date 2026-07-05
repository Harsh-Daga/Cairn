import { useState } from "react";
import type { Span } from "@/lib/types";
import { Chip } from "@/components/common/Chip";
import { formatTokens } from "@/lib/format";

type InspectorTab = "summary" | "text" | "waste";

interface SpanInspectorProps {
  span: Span | null;
}

export function SpanInspector({ span }: SpanInspectorProps) {
  const [tab, setTab] = useState<InspectorTab>("summary");

  if (!span) {
    return (
      <div className="card flex h-full items-center justify-center p-4 text-sm text-cinder">
        Select a span to inspect
      </div>
    );
  }

  const estimated = span.input_estimated > 0 || span.output_estimated > 0;
  const hasWaste = span.waste_tokens > 0 || span.waste_category != null;

  return (
    <div className="card flex h-full flex-col overflow-hidden">
      <div className="flex border-b border-quartz-vein">
        {(["summary", "text", "waste"] as const).map((t) => (
          <button
            key={t}
            type="button"
            className={`flex-1 px-3 py-2 font-mono text-[10px] uppercase tracking-wide ${
              tab === t ? "border-b-2 border-copper text-bone" : "text-cinder hover:text-bone"
            }`}
            onClick={() => setTab(t)}
          >
            {t}
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
              <div className="flex justify-between">
                <dt className="text-cinder">seq</dt>
                <dd>{span.seq}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-cinder">tokens in/out</dt>
                <dd className={estimated ? "estimated-chip" : ""}>
                  {formatTokens(span.input_tokens ?? 0)} / {formatTokens(span.output_tokens ?? 0)}
                </dd>
              </div>
              {span.context_tokens_after != null ? (
                <div className="flex justify-between">
                  <dt className="text-cinder">context after</dt>
                  <dd>{formatTokens(span.context_tokens_after)}</dd>
                </div>
              ) : null}
              {span.path_rel ? (
                <div className="flex justify-between gap-4">
                  <dt className="text-cinder">path</dt>
                  <dd className="truncate text-right">{span.path_rel}</dd>
                </div>
              ) : null}
            </dl>
          </>
        ) : null}
        {tab === "text" ? (
          span.text_inline ? (
            <pre className="max-h-full overflow-auto rounded-sm bg-granite/40 p-3 font-mono text-[10px] text-bone">
              {span.text_inline.slice(0, 4000)}
            </pre>
          ) : (
            <p className="text-sm text-cinder">No inline text for this span.</p>
          )
        ) : null}
        {tab === "waste" ? (
          hasWaste ? (
            <dl className="space-y-3 font-mono text-[11px]">
              {span.waste_category ? (
                <div>
                  <dt className="text-cinder">category</dt>
                  <dd className="mt-1 text-ochre">{span.waste_category}</dd>
                </div>
              ) : null}
              <div>
                <dt className="text-cinder">waste tokens</dt>
                <dd className="mt-1 text-bone">{formatTokens(span.waste_tokens)}</dd>
              </div>
              <p className="text-xs text-cinder">
                Waste spans are re-billed on subsequent turns when context is retained.
              </p>
            </dl>
          ) : (
            <p className="text-sm text-cinder">No waste flagged on this span.</p>
          )
        ) : null}
      </div>
    </div>
  );
}
