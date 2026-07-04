import type { Span } from "@/lib/types";
import { formatTokens } from "@/lib/format";

interface ReplayScrubberProps {
  maxSeq: number;
  seq: number;
  spans: Span[];
  onChange: (seq: number) => void;
}

export function ReplayScrubber({ maxSeq, seq, spans, onChange }: ReplayScrubberProps) {
  const ctx = [...spans].reverse().find((s) => s.context_tokens_after)?.context_tokens_after;
  const files = new Set(spans.map((s) => s.path_rel).filter(Boolean)).size;
  const agents = new Set(spans.map((s) => s.agent_id).filter(Boolean)).size;

  return (
    <div className="card p-4">
      <div className="flex items-center gap-4">
        <input
          type="range"
          min={0}
          max={maxSeq}
          value={seq}
          className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-granite accent-copper"
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label="Replay scrubber"
        />
        <button
          type="button"
          className="rounded-sm border border-quartz-vein px-3 py-1 font-mono text-xs text-copper hover:bg-shale"
          onClick={() => onChange(Math.min(maxSeq, seq + 1))}
        >
          Step →
        </button>
      </div>
      <p className="mt-2 font-mono text-[11px] text-cinder">
        turn {seq} · {ctx ? formatTokens(ctx) : "—"} ctx · files read {files} · {agents} agents
      </p>
    </div>
  );
}

interface ContextTimelineProps {
  spans: Span[];
  selectedId: string | null;
  onSelect: (spanId: string) => void;
}

export function ContextTimeline({ spans, selectedId, onSelect }: ContextTimelineProps) {
  const points = spans.filter((s) => s.context_tokens_after != null);
  const maxCtx = Math.max(1, ...points.map((s) => s.context_tokens_after ?? 0));

  return (
    <div className="card p-3">
      <h4 className="mb-2 font-mono text-[10px] uppercase tracking-wide text-cinder">Context strata</h4>
      <div className="flex h-24 items-end gap-0.5">
        {points.map((span) => {
          const h = ((span.context_tokens_after ?? 0) / maxCtx) * 100;
          const selected = selectedId === span.span_id;
          return (
            <button
              key={span.span_id}
              type="button"
              data-timeline-span={span.span_id}
              className={`min-w-[4px] flex-1 rounded-t-sm bg-patina/70 hover:bg-copper/80 ${
                selected ? "ring-1 ring-copper" : ""
              }`}
              style={{ height: `${h}%` }}
              title={`seq ${span.seq}`}
              onClick={() => onSelect(span.span_id)}
            />
          );
        })}
      </div>
    </div>
  );
}
