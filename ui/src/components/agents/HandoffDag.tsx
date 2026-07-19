import dagre from "dagre";
import { useMemo } from "react";
import { chartColors } from "@/components/charts/chartTheme";

interface HandoffEdge {
  from_agent?: string | null;
  to_agent?: string | null;
  from_span_id?: string;
  to_span_id?: string;
  link_type?: string;
}

interface HandoffDagProps {
  handoffs: HandoffEdge[];
  width?: number;
  height?: number;
  className?: string;
}

function nodeId(h: HandoffEdge, side: "from" | "to"): string {
  if (side === "from") {
    return String(h.from_agent ?? h.from_span_id ?? "?");
  }
  return String(h.to_agent ?? h.to_span_id ?? "?");
}

export function HandoffDag({ handoffs, width = 640, height = 240, className }: HandoffDagProps) {
  const { nodes, edges } = useMemo(() => {
    const g = new dagre.graphlib.Graph();
    g.setGraph({ rankdir: "LR", nodesep: 36, ranksep: 72, marginx: 16, marginy: 16 });
    g.setDefaultEdgeLabel(() => ({}));

    const ids = new Set<string>();
    for (const h of handoffs) {
      ids.add(nodeId(h, "from"));
      ids.add(nodeId(h, "to"));
    }
    for (const id of ids) {
      g.setNode(id, { width: 96, height: 28, label: id });
    }
    for (const h of handoffs) {
      g.setEdge(nodeId(h, "from"), nodeId(h, "to"));
    }
    dagre.layout(g);

    const laidOut = g.nodes().map((id) => {
      const n = g.node(id);
      return { id, x: n.x, y: n.y, width: n.width, height: n.height };
    });
    const edgePaths = g.edges().map((e) => {
      const edge = g.edge(e);
      return { from: e.v, to: e.w, points: edge.points as { x: number; y: number }[] };
    });
    return { nodes: laidOut, edges: edgePaths };
  }, [handoffs]);

  if (handoffs.length === 0) {
    return <p className="p-4 text-sm text-cinder">No handoff links in this window.</p>;
  }

  return (
    <svg
      width={width}
      height={height}
      className={className}
      role="img"
      aria-label="Agent handoff diagram"
    >
      {edges.map((edge) => {
        const pts = edge.points;
        if (!pts || pts.length < 2) return null;
        const d = pts.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
        return (
          <path
            key={`${edge.from}-${edge.to}`}
            d={d}
            fill="none"
            stroke={chartColors.grid}
            strokeWidth={1.5}
            markerEnd="url(#handoff-arrow)"
          />
        );
      })}
      <defs>
        <marker
          id="handoff-arrow"
          viewBox="0 0 10 10"
          refX={8}
          refY={5}
          markerWidth={6}
          markerHeight={6}
          orient="auto-start-reverse"
        >
          <path d="M 0 0 L 10 5 L 0 10 z" fill={chartColors.muted} />
        </marker>
      </defs>
      {nodes.map((node) => (
        <g key={node.id}>
          <rect
            x={node.x - node.width / 2}
            y={node.y - node.height / 2}
            width={node.width}
            height={node.height}
            rx={4}
            fill="var(--granite)"
            stroke={chartColors.stroke}
            strokeWidth={1}
          />
          <text
            x={node.x}
            y={node.y}
            textAnchor="middle"
            dominantBaseline="middle"
            fill={chartColors.text}
            fontSize={10}
            fontFamily="var(--font-mono)"
          >
            {node.id.length > 12 ? `${node.id.slice(0, 10)}…` : node.id}
          </text>
        </g>
      ))}
    </svg>
  );
}
