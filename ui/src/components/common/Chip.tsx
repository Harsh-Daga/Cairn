import type { ReactNode } from "react";

interface ChipProps {
  label: string;
  tone?: "default" | "copper" | "patina" | "cinnabar" | "malachite" | "ochre" | "estimated";
  className?: string;
}

export function Chip({ label, tone = "default", className = "" }: ChipProps) {
  const toneClass =
    tone === "copper"
      ? "border-copper/40 text-copper"
      : tone === "patina"
        ? "border-patina/40 text-patina"
        : tone === "cinnabar"
          ? "border-cinnabar/40 text-cinnabar"
          : tone === "malachite"
            ? "border-malachite/40 text-malachite"
            : tone === "ochre"
              ? "border-ochre/40 text-ochre"
              : tone === "estimated"
              ? "estimated-chip border-cinder/40 text-cinder"
              : "border-quartz-vein text-cinder";

  return (
    <span
      className={`inline-flex items-center rounded-chip border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide ${toneClass} ${className}`}
    >
      {label}
    </span>
  );
}

interface ChartFrameProps {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
}

export function ChartFrame({ title, subtitle, children, action }: ChartFrameProps) {
  return (
    <section className="card overflow-hidden">
      <div className="flex items-start justify-between gap-4 border-b border-quartz-vein/80 px-5 py-4">
        <div>
          <h3 className="font-display text-base font-medium text-bone">{title}</h3>
          {subtitle ? <p className="mt-1 font-mono text-[10px] text-cinder">{subtitle}</p> : null}
        </div>
        {action}
      </div>
      <div className="chart-surface p-5">{children}</div>
    </section>
  );
}
