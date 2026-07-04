import type { Span } from "@/lib/types";
import { Chip } from "@/components/common/Chip";
import { formatTokens } from "@/lib/format";

interface SpanInspectorProps {
  span: Span | null;
}

export function SpanInspector({ span }: SpanInspectorProps) {
  if (!span) {
    return (
      <div className="card flex h-full items-center justify-center p-4 text-sm text-cinder">
        Select a span to inspect
      </div>
    );
  }

  const estimated = span.input_estimated > 0 || span.output_estimated > 0;

  return (
    <div className="card h-full overflow-auto p-4">
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
      {span.text_inline ? (
        <pre className="mt-4 max-h-48 overflow-auto rounded-sm bg-granite/40 p-3 font-mono text-[10px] text-bone">
          {span.text_inline.slice(0, 2000)}
        </pre>
      ) : null}
    </div>
  );
}
