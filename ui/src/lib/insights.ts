import type { InsightRow } from "@/lib/types";

export function splitInsights(insights: InsightRow[]) {
  return {
    recommendations: insights.filter((insight) => !insight.diagnostic),
    diagnostics: insights.filter((insight) => insight.diagnostic),
  };
}
