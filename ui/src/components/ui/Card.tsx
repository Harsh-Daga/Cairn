import { useId, type ReactNode } from "react";
import { EstimateBadge } from "./Indicators";

export interface MetricHelpProps {
  definition: string;
  calculation?: string;
  source?: string;
  limitations?: string;
}

export function MetricHelp({ definition, calculation, source, limitations }: MetricHelpProps) {
  const id = useId();
  return (
    <details className="group relative inline-block">
      <summary
        aria-controls={id}
        className="inline-flex min-h-7 min-w-7 cursor-pointer list-none items-center justify-center rounded-full border border-quartz-vein text-xs text-cinder hover:text-bone"
      >
        <span aria-hidden="true">?</span>
        <span className="sr-only">Explain this metric</span>
      </summary>
      <div
        id={id}
        className="absolute right-0 z-40 mt-2 w-72 rounded-sm border border-quartz-vein bg-overlay p-3 text-left text-xs text-cinder shadow-stone"
      >
        <p className="text-bone">{definition}</p>
        {calculation ? (
          <p className="mt-2">
            <strong className="text-bone">Calculation:</strong> {calculation}
          </p>
        ) : null}
        {source ? (
          <p className="mt-2">
            <strong className="text-bone">Source:</strong> {source}
          </p>
        ) : null}
        {limitations ? (
          <p className="mt-2">
            <strong className="text-bone">Limitations:</strong> {limitations}
          </p>
        ) : null}
      </div>
    </details>
  );
}

interface CardProps {
  title?: string;
  subtitle?: string;
  action?: ReactNode;
  metricHelp?: MetricHelpProps;
  children: ReactNode;
  className?: string;
  interactive?: boolean;
}

export function Card({
  title,
  subtitle,
  action,
  metricHelp,
  children,
  className = "",
  interactive = false,
}: CardProps) {
  const titleId = useId();
  return (
    <section
      className={`card ${interactive ? "card--interactive" : ""} ${className}`.trim()}
      aria-labelledby={title ? titleId : undefined}
    >
      {title || subtitle || action || metricHelp ? (
        <header className="flex items-start justify-between gap-4 border-b border-quartz-vein/80 px-5 py-4">
          <div>
            {title ? (
              <h2 id={titleId} className="font-display text-[15px] font-semibold text-bone">
                {title}
              </h2>
            ) : null}
            {subtitle ? <p className="mt-1 text-xs text-cinder">{subtitle}</p> : null}
          </div>
          <div className="flex items-center gap-2">
            {metricHelp ? <MetricHelp {...metricHelp} /> : null}
            {action}
          </div>
        </header>
      ) : null}
      {children}
    </section>
  );
}

interface StatProps {
  label: string;
  value: ReactNode;
  /** Page KPI card body copy. When set, renders the card+detail grammar used by analyze pages. */
  detail?: string;
  delta?: string;
  deltaDirection?: "up" | "down" | "flat";
  estimated?: boolean;
  sparkline?: ReactNode;
  help?: MetricHelpProps;
}

/** Compact prior-period metric (bare) or analyze-page KPI card (when `detail` is set). */
export function Stat({
  label,
  value,
  detail,
  delta,
  deltaDirection = "flat",
  estimated = false,
  sparkline,
  help,
}: StatProps) {
  if (detail !== undefined) {
    return (
      <div className="card p-4">
        <div className="flex items-center justify-between gap-2">
          <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">{label}</p>
          <div className="flex items-center gap-2">
            {estimated ? <EstimateBadge /> : null}
            {help ? <MetricHelp {...help} /> : null}
          </div>
        </div>
        <p className="mt-1 font-display text-2xl text-bone">{value}</p>
        <p className="mt-1 text-xs leading-5 text-cinder">{detail}</p>
      </div>
    );
  }
  const deltaSymbol = deltaDirection === "up" ? "↑" : deltaDirection === "down" ? "↓" : "→";
  return (
    <div>
      <div className="flex items-center gap-2 text-xs text-cinder">
        <span>{label}</span>
        {help ? <MetricHelp {...help} /> : null}
      </div>
      <div className="mt-2 flex items-end justify-between gap-3">
        <p className={`font-mono text-2xl text-bone ${estimated ? "estimated-chip" : ""}`}>
          {value}
          {estimated ? <span className="sr-only"> estimated</span> : null}
        </p>
        {sparkline}
      </div>
      {delta ? (
        <p className="mt-1 font-mono text-xs text-cinder">
          <span aria-hidden="true">{deltaSymbol}</span>
          <span className="sr-only">{deltaDirection}</span> {delta} from prior period
        </p>
      ) : null}
    </div>
  );
}
