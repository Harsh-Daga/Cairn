export interface SpanLinkRow {
  from_span_id: string;
  to_span_id: string;
  link_type: string;
}

export interface LinkConnector {
  id: string;
  fromIndex: number;
  toIndex: number;
  linkType: "retry_of" | "handoff";
}

export function pairLinkConnectors(
  links: SpanLinkRow[],
  spanIndex: Map<string, number>,
): LinkConnector[] {
  const connectors: LinkConnector[] = [];
  for (const link of links) {
    if (link.link_type !== "retry_of" && link.link_type !== "handoff") {
      continue;
    }
    const fromIndex = spanIndex.get(link.from_span_id);
    const toIndex = spanIndex.get(link.to_span_id);
    if (fromIndex == null || toIndex == null) continue;
    connectors.push({
      id: `${link.from_span_id}-${link.to_span_id}-${link.link_type}`,
      fromIndex,
      toIndex,
      linkType: link.link_type,
    });
  }
  return connectors;
}

export function connectorsForSpan(
  connectors: LinkConnector[],
  spanId: string,
  spanIndex: Map<string, number>,
): LinkConnector[] {
  const index = spanIndex.get(spanId);
  if (index == null) return [];
  return connectors.filter((c) => c.fromIndex === index || c.toIndex === index);
}
