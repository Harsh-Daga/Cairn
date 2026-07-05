import type { VerdictPreviewData } from "@/lib/types";

export function formatVerdictPreview(preview: VerdictPreviewData): string {
  if (preview.traffic_unknown) {
    return "Verdict timing unknown (<5 traces/week)";
  }
  const days = preview.expected_days_to_verdict;
  if (days == null) {
    return "Verdict timing unknown";
  }
  const rounded = Math.max(1, Math.round(days));
  return `Verdict in ~${rounded} days at current traffic`;
}

export function VerdictPreview({ preview }: { preview: VerdictPreviewData }) {
  return (
    <p className="mt-1 font-mono text-[10px] text-cinder">{formatVerdictPreview(preview)}</p>
  );
}
