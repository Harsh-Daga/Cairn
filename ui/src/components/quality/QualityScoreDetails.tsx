import { Chip } from "@/components/common/Chip";

interface QualityScoreDetailsProps {
  score: number;
  components?: Record<string, number> | null;
  weights?: Record<string, number> | null;
}

export function QualityScoreDetails({ score, components, weights }: QualityScoreDetailsProps) {
  const rows = Object.entries(components ?? {});
  return (
    <details className="group">
      <summary className="cursor-pointer list-none">
        <Chip label={`${score.toFixed(1)} quality`} tone="patina" />
      </summary>
      <div className="mt-2 min-w-56 rounded-sm border border-quartz-vein bg-slate p-3 shadow-stone">
        <p className="font-mono text-[10px] uppercase tracking-wide text-cinder">
          Component × weight
        </p>
        <dl className="mt-2 space-y-1 font-mono text-[10px]">
          {rows.map(([name, value]) => {
            const weight = Number(weights?.[name] ?? 0);
            return (
              <div key={name} className="flex justify-between gap-4">
                <dt className="text-cinder">{name.replaceAll("_", " ")}</dt>
                <dd className="text-bone">
                  {(value * 100).toFixed(0)}% × {(weight * 100).toFixed(0)}%
                </dd>
              </div>
            );
          })}
        </dl>
      </div>
    </details>
  );
}
