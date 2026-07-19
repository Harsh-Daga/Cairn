import type { QueryFilterToken } from "@/lib/types";

const SHAREABLE_FIELDS = new Set([
  "source",
  "status",
  "cost",
  "outcome",
  "tool",
  "after",
  "verification",
]);

export function privacySafeFilterQuery(tokens: QueryFilterToken[]): string {
  return tokens
    .filter((token) => token.available && SHAREABLE_FIELDS.has(token.field))
    .map((token) => token.raw)
    .join(" ");
}

export function privacySafeFilterUrl(currentUrl: string, tokens: QueryFilterToken[]): string {
  const url = new URL(currentUrl);
  url.searchParams.delete("q");
  url.searchParams.delete("agent");
  url.searchParams.delete("file");
  const query = privacySafeFilterQuery(tokens);
  if (query) url.searchParams.set("q", query);
  return url.toString();
}
