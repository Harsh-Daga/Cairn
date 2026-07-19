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

export { ChartFrame } from "@/components/charts/ChartFrame";
