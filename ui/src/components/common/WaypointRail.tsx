import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useUiStore } from "@/state/ui";
import { fetchExperiments, fetchInsights, fetchWorkspace } from "@/lib/api";
import { formatTokens } from "@/lib/format";
import { CairnGlyph } from "./CairnGlyph";
import { Gauge } from "@/components/charts/Gauge";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  badge?: number | "dot" | "pulse";
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: "⛰" },
  { to: "/sessions", label: "Sessions", icon: "◎" },
  { to: "/sessions/diff", label: "Session diff", icon: "⇄" },
  { to: "/context", label: "Context", icon: "▤" },
  { to: "/agents", label: "Agents", icon: "⬡" },
  { to: "/behavior", label: "Behavior", icon: "〜" },
  { to: "/quality", label: "Quality", icon: "✦" },
  { to: "/insights", label: "Insights", icon: "◈" },
  { to: "/optimize", label: "Optimize", icon: "↻" },
  { to: "/live", label: "Live", icon: "●" },
  { to: "/search", label: "Search", icon: "⌕" },
];

function NavBadge({ badge }: { badge: number | "dot" | "pulse" }) {
  if (badge === "dot") {
    return <span className="ml-auto h-1.5 w-1.5 rounded-full bg-copper" aria-hidden="true" />;
  }
  if (badge === "pulse") {
    return (
      <span
        className="ml-auto h-1.5 w-1.5 rounded-full bg-malachite animate-[pulse-once_1s_ease-out_infinite]"
        aria-hidden="true"
      />
    );
  }
  if (badge > 0) {
    return (
      <span className="ml-auto rounded-chip bg-copper/20 px-1.5 font-mono text-[10px] text-copper">
        {badge}
      </span>
    );
  }
  return null;
}

export function WaypointRail() {
  const collapsed = useUiStore((s) => s.railCollapsed);
  const watchEnabled = useUiStore((s) => s.watchEnabled);
  const toggleRail = useUiStore((s) => s.toggleRail);

  const { data: insights } = useQuery({
    queryKey: ["insights", "rail"],
    queryFn: () => fetchInsights(),
    staleTime: 30_000,
  });
  const { data: experiments } = useQuery({
    queryKey: ["experiments", "rail"],
    queryFn: fetchExperiments,
    staleTime: 30_000,
  });
  const { data: workspace } = useQuery({
    queryKey: ["workspace"],
    queryFn: fetchWorkspace,
    staleTime: 60_000,
  });

  const newInsights = (insights?.insights ?? []).filter((i) => i.state === "new").length;
  const proposedCount = (experiments?.experiments ?? []).filter((e) => e.status === "proposed").length;
  const gauge = workspace?.gauge;
  const gaugePct =
    gauge?.limit && gauge.limit > 0
      ? Math.min(100, (gauge.total_tokens / gauge.limit) * 100)
      : 0;
  const gaugeDetail = gauge?.limit
    ? `${formatTokens(gauge.total_tokens)} / ${formatTokens(gauge.limit)}`
    : gauge
      ? `${formatTokens(gauge.total_tokens)} tok · no limit`
      : undefined;

  const navItems: NavItem[] = NAV_ITEMS.map((item) => {
    if (item.to === "/insights") return { ...item, badge: newInsights || undefined };
    if (item.to === "/optimize") return { ...item, badge: proposedCount > 0 ? "dot" : undefined };
    if (item.to === "/live") return { ...item, badge: watchEnabled ? "pulse" : undefined };
    return item;
  });

  return (
    <aside
      className={`flex flex-col border-r border-quartz-vein bg-slate transition-all duration-150 ${
        collapsed ? "w-[72px]" : "w-[240px]"
      }`}
      aria-label="Main navigation"
    >
      <div
        className={`flex items-center gap-2.5 border-b border-quartz-vein px-4 py-4 ${
          collapsed ? "justify-center" : ""
        }`}
      >
        <CairnGlyph />
        {!collapsed && (
          <div>
            <div className="display text-base tracking-widest text-bone">CAIRN</div>
            <div className="mono text-[10px] text-cinder">field notebook</div>
          </div>
        )}
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto p-2">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[13px] font-medium transition-colors ${
                isActive
                  ? "bg-granite text-bone shadow-[inset_2px_0_0_0_var(--copper)]"
                  : "text-cinder hover:bg-shale hover:text-bone"
              } ${collapsed ? "justify-center" : ""}`
            }
          >
            <span className="text-sm" aria-hidden="true">
              {item.icon}
            </span>
            {!collapsed && <span className="flex-1">{item.label}</span>}
            {!collapsed && item.badge !== undefined ? <NavBadge badge={item.badge} /> : null}
          </NavLink>
        ))}

        <div className="flex-1" />
        <div className="mx-1 my-2 h-px bg-quartz-vein" />

        <NavLink
          to="/settings"
          className={({ isActive }) =>
            `flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[13px] font-medium ${
              isActive ? "bg-granite text-bone" : "text-cinder hover:bg-shale hover:text-bone"
            } ${collapsed ? "justify-center" : ""}`
          }
        >
          <span aria-hidden="true">⚙</span>
          {!collapsed && <span>Settings</span>}
        </NavLink>
      </nav>

      {!collapsed && gauge && (gauge.total_tokens > 0 || gauge.limit != null) ? (
        <div className="border-t border-quartz-vein px-3 py-3">
          <Gauge
            value={gaugePct}
            label={`plan window · ${gauge.window_hours}h${gauge.exceeded ? " · exceeded" : ""}`}
            detail={gaugeDetail}
            width={216}
          />
        </div>
      ) : null}

      <button
        type="button"
        onClick={toggleRail}
        className="mx-3 mb-3 self-end rounded-chip border border-quartz-vein px-1.5 py-0.5 font-mono text-[11px] text-cinder hover:text-bone"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? "»" : "«"}
      </button>
    </aside>
  );
}
