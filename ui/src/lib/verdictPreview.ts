import type { VerdictPreviewData } from "@/lib/types";

export function formatVerdictPreview(preview: VerdictPreviewData): string {
  if (preview.traffic_unknown) return "Verdict timing unknown (<5 traces/week)";
  const days = preview.expected_days_to_verdict;
  if (days == null) return "Verdict timing unknown";
  return `Verdict in ~${Math.max(1, Math.round(days))} days at current traffic`;
}
