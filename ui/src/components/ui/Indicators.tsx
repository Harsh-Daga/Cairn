import type { ReactNode } from "react";

type BadgeTone = "neutral" | "info" | "warning" | "high" | "critical" | "success";

const TONES: Record<BadgeTone, string> = {
  neutral: "border-border-default text-cinder",
  info: "border-info/50 text-info",
  warning: "border-warning/50 text-warning",
  high: "border-high/50 text-high",
  critical: "border-critical/50 text-critical",
  success: "border-malachite/50 text-malachite",
};

export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: BadgeTone }) {
  return (
    <span
      className={`inline-flex items-center rounded-chip border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

export function EstimateBadge({ label = "Estimated" }: { label?: string }) {
  return <span className="estimated-chip font-mono text-[10px] text-estimate">{label}</span>;
}

export function ConfidenceInterval({
  low,
  estimate,
  high,
  format = (value) => String(value),
}: {
  low: number;
  estimate: number;
  high: number;
  format?: (value: number) => string;
}) {
  const minimum = Math.min(low, high);
  const maximum = Math.max(low, high);
  const position =
    maximum === minimum
      ? 50
      : ((Math.min(maximum, Math.max(minimum, estimate)) - minimum) / (maximum - minimum)) * 100;
  return (
    <div
      className="confidence-chip py-1 font-mono text-xs text-cinder"
      aria-label={`Estimate ${format(estimate)}; confidence interval ${format(minimum)} to ${format(maximum)}`}
    >
      <div className="relative h-1 rounded-full bg-confidence/25" aria-hidden="true">
        <span
          className="absolute -top-1 h-3 w-0.5 bg-confidence"
          style={{ left: `${position}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between">
        <span>{format(minimum)}</span>
        <strong className="text-bone">{format(estimate)}</strong>
        <span>{format(maximum)}</span>
      </div>
    </div>
  );
}
