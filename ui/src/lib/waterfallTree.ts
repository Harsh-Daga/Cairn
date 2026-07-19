import type { Span, SpanNode } from "@/lib/types";

export interface FlatRow {
  span: Span;
  depth: number;
}

export function flattenTree(nodes: SpanNode[], depth = 0, foldSubagents = false): FlatRow[] {
  const rows: FlatRow[] = [];
  const stack = [...nodes].reverse().map((node) => ({ node, nodeDepth: depth }));
  while (stack.length > 0) {
    const current = stack.pop();
    if (!current) break;
    const { node, nodeDepth } = current;
    rows.push({ span: node.span, depth: nodeDepth });
    const skipChildren = foldSubagents && node.span.kind === "subagent";
    if (node.children.length > 0 && !skipChildren) {
      for (let index = node.children.length - 1; index >= 0; index -= 1) {
        const child = node.children[index];
        if (child) stack.push({ node: child, nodeDepth: nodeDepth + 1 });
      }
    }
  }
  return rows;
}
