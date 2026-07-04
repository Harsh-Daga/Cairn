import { chartColors } from "./chartTheme";

export interface GaugeProps {
  /** 0–100 fill percentage */
  value: number;
  label?: string;
  detail?: string;
  warnAbove?: number;
  width?: number;
  height?: number;
  className?: string;
}

export function Gauge({
  value,
  label = "plan window",
  detail,
  warnAbove = 80,
  width = 200,
  height = 36,
  className,
}: GaugeProps) {
  const pct = Math.min(100, Math.max(0, value));
  const warn = pct >= warnAbove;

  return (
    <div className={className} style={{ width }} aria-label={label}>
      <div className="mb-1.5 font-mono text-[10px] text-cinder">{label}</div>
      <div
        className="overflow-hidden rounded-sm bg-granite"
        style={{ height: Math.max(5, height - 20) }}
        role="meter"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div
          className={`h-full rounded-sm transition-[width] duration-200 ${warn ? "bg-cinnabar" : "bg-copper"}`}
          style={{ width: `${pct}%`, backgroundColor: warn ? chartColors.fillWarn : chartColors.fill }}
        />
      </div>
      {detail ? <div className="mt-1.5 font-mono text-[10px] text-bone">{detail}</div> : null}
    </div>
  );
}
