import type { VerdictPreviewData } from "@/lib/types";
import { formatVerdictPreview } from "@/lib/verdictPreview";

export function VerdictPreview({ preview }: { preview: VerdictPreviewData }) {
  return <p className="mt-1 font-mono text-[10px] text-cinder">{formatVerdictPreview(preview)}</p>;
}
