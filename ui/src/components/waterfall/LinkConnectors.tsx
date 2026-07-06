import type { LinkConnector } from "@/lib/spanLinks";

const ROW_HEIGHT = 32;
const GUTTER_WIDTH = 20;

interface LinkConnectorsProps {
  connectors: LinkConnector[];
  totalRows: number;
  highlightedId: string | null;
  onHover: (connectorId: string | null) => void;
}

function arcPath(fromY: number, toY: number): string {
  const x0 = GUTTER_WIDTH - 2;
  const x1 = 4;
  const midY = (fromY + toY) / 2;
  return `M ${x0} ${fromY} Q ${x1} ${midY} ${x0} ${toY}`;
}

export function LinkConnectors({
  connectors,
  totalRows,
  highlightedId,
  onHover,
}: LinkConnectorsProps) {
  if (connectors.length === 0) return null;

  const height = Math.max(totalRows * ROW_HEIGHT, ROW_HEIGHT);

  return (
    <svg
      className="pointer-events-none absolute left-0 top-[33px] z-[5]"
      width={GUTTER_WIDTH}
      height={height}
      aria-hidden="true"
    >
      {connectors.map((connector) => {
        const fromY = connector.fromIndex * ROW_HEIGHT + ROW_HEIGHT / 2;
        const toY = connector.toIndex * ROW_HEIGHT + ROW_HEIGHT / 2;
        const active = highlightedId === connector.id;
        const isRetry = connector.linkType === "retry_of";
        return (
          <path
            key={connector.id}
            d={arcPath(fromY, toY)}
            fill="none"
            stroke={isRetry ? "var(--color-cinnabar)" : "var(--color-patina)"}
            strokeWidth={active ? 2.5 : 1.5}
            strokeDasharray={isRetry ? "4 3" : undefined}
            opacity={active ? 1 : 0.75}
            className="pointer-events-auto cursor-pointer"
            onMouseEnter={() => onHover(connector.id)}
            onMouseLeave={() => onHover(null)}
          />
        );
      })}
    </svg>
  );
}

export function LinkLegend({ links }: { links: { link_type: string }[] }) {
  if (links.length === 0) return null;
  const hasRetry = links.some((c) => c.link_type === "retry_of");
  const hasHandoff = links.some((c) => c.link_type === "handoff");
  return (
    <div className="mb-2 flex flex-wrap gap-2">
      {hasRetry ? (
        <span className="rounded-chip border border-cinnabar/40 px-2 py-0.5 font-mono text-[10px] text-cinnabar">
          retry link
        </span>
      ) : null}
      {hasHandoff ? (
        <span className="rounded-chip border border-patina/40 px-2 py-0.5 font-mono text-[10px] text-patina">
          handoff link
        </span>
      ) : null}
    </div>
  );
}
