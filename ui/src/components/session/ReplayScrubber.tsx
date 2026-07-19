import { useEffect, useState } from "react";
import type { Span } from "@/lib/types";
import { formatTokens } from "@/lib/format";
import { Sparkline } from "@/components/charts";

interface ReplayScrubberProps {
  maxSeq: number;
  seq: number;
  spans: Span[];
  onChange: (seq: number) => void;
}

export function ReplayScrubber({ maxSeq, seq, spans, onChange }: ReplayScrubberProps) {
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<1 | 4 | 16>(1);
  const ctx = [...spans].reverse().find((s) => s.context_tokens_after)?.context_tokens_after;
  const files = new Set(spans.map((s) => s.path_rel).filter(Boolean)).size;
  const actors = new Set(spans.map((s) => s.agent_id).filter(Boolean)).size;

  useEffect(() => {
    if (!playing || maxSeq <= 0) return;
    if (seq >= maxSeq) {
      setPlaying(false);
      return;
    }
    const timer = window.setInterval(
      () => onChange(Math.min(maxSeq, seq + 1)),
      Math.max(60, 800 / speed),
    );
    return () => window.clearInterval(timer);
  }, [maxSeq, onChange, playing, seq, speed]);

  return (
    <div className="card p-4" aria-label="Session replay">
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          aria-pressed={playing}
          className="min-w-20 rounded-sm border border-quartz-vein px-3 py-1 font-mono text-xs text-copper hover:bg-shale"
          onClick={() => {
            if (seq >= maxSeq) onChange(0);
            setPlaying((value) => !value);
          }}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <input
          type="range"
          min={0}
          max={maxSeq}
          value={seq}
          className="h-2 flex-1 cursor-pointer appearance-none rounded-full bg-granite accent-copper"
          onChange={(e) => onChange(Number(e.target.value))}
          aria-label="Replay scrubber"
        />
        <div className="flex" role="group" aria-label="Replay speed">
          {([1, 4, 16] as const).map((value) => (
            <button
              key={value}
              type="button"
              aria-pressed={speed === value}
              className={`border border-quartz-vein px-2 py-1 font-mono text-xs first:rounded-l-sm last:rounded-r-sm ${
                speed === value ? "bg-copper/10 text-copper" : "text-cinder hover:text-bone"
              }`}
              onClick={() => setSpeed(value)}
            >
              {value}×
            </button>
          ))}
        </div>
        <button
          type="button"
          className="rounded-sm border border-quartz-vein px-3 py-1 font-mono text-xs text-copper hover:bg-shale"
          onClick={() => {
            setPlaying(false);
            onChange(Math.min(maxSeq, seq + 1));
          }}
        >
          Step →
        </button>
      </div>
      <p className="mt-2 font-mono text-[11px] text-cinder" aria-live="polite">
        turn {seq} of {maxSeq} · {ctx ? formatTokens(ctx) : "—"} ctx · files read {files} · {actors}{" "}
        actors
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
  const data = points.map((s) => s.context_tokens_after ?? 0);
  const selectedIndex = points.findIndex((span) => span.span_id === selectedId);
  const moveViewport = (direction: -1 | 1) => {
    const origin = selectedIndex >= 0 ? selectedIndex : direction > 0 ? -1 : points.length;
    const next = points[Math.max(0, Math.min(points.length - 1, origin + direction))];
    if (next) onSelect(next.span_id);
  };

  return (
    <div className="card p-3" aria-label="Context minimap">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h4 className="font-mono text-[10px] uppercase tracking-wide text-cinder">
          Context minimap
        </h4>
        <div className="flex" role="group" aria-label="Minimap viewport controls">
          <button
            type="button"
            className="rounded-l-sm border border-quartz-vein px-2 py-1 text-xs text-cinder hover:text-bone"
            onClick={() => moveViewport(-1)}
            disabled={points.length === 0}
            aria-label="Previous context point"
          >
            ←
          </button>
          <button
            type="button"
            className="rounded-r-sm border border-quartz-vein px-2 py-1 text-xs text-cinder hover:text-bone"
            onClick={() => moveViewport(1)}
            disabled={points.length === 0}
            aria-label="Next context point"
          >
            →
          </button>
        </div>
      </div>
      <div className="relative h-24">
        <Sparkline data={data} width={320} height={96} className="w-full max-w-full" />
        <div className="absolute inset-0 flex">
          {points.map((span) => {
            const selected = selectedId === span.span_id;
            return (
              <button
                key={span.span_id}
                type="button"
                data-timeline-span={span.span_id}
                className={`min-w-[4px] flex-1 ${selected ? "bg-copper/20 ring-1 ring-copper" : ""}`}
                title={`seq ${span.seq}`}
                onClick={() => onSelect(span.span_id)}
                aria-label={`Select span ${span.seq}`}
              />
            );
          })}
        </div>
      </div>
      {data.length > 0 ? (
        <p className="mt-2 font-mono text-[10px] text-cinder">
          peak {formatTokens(Math.max(...data))} ctx
        </p>
      ) : null}
    </div>
  );
}
