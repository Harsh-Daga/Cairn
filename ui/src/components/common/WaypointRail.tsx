import { NavLink } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useUiStore } from "@/state/ui";
import { fetchExperiments, fetchInsights, fetchWorkspace } from "@/lib/api";
import { formatTokens } from "@/lib/format";
import { CairnGlyph } from "./CairnGlyph";
import { Gauge } from "@/components/charts/Gauge";
import { NAVIGATION_GROUPS, NAVIGATION_ITEMS, type NavigationItem } from "@/lib/navigation";

type RailItem = NavigationItem & { badge?: number | "dot" | "pulse" };

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
  const proposedCount = (experiments?.experiments ?? []).filter(
    (e) => e.status === "proposed",
  ).length;
  const gauge = workspace?.gauge;
  const gaugePct =
    gauge?.limit && gauge.limit > 0 ? Math.min(100, (gauge.total_tokens / gauge.limit) * 100) : 0;
  const gaugeDetail = gauge?.limit
    ? `${formatTokens(gauge.total_tokens)} / ${formatTokens(gauge.limit)}`
    : gauge
      ? `${formatTokens(gauge.total_tokens)} tok · no limit`
      : undefined;

  const navItems: RailItem[] = NAVIGATION_ITEMS.map((item) => {
    if (item.to === "/insights") return { ...item, badge: newInsights || undefined };
    if (item.to === "/optimize") return { ...item, badge: proposedCount > 0 ? "dot" : undefined };
    if (item.to === "/live") return { ...item, badge: watchEnabled ? "pulse" : undefined };
    return item;
  });

  return (
    <aside
      className={`waypoint-rail flex flex-col border-r border-quartz-vein/80 bg-slate/95 shadow-[12px_0_36px_rgb(var(--overlay-scrim-rgb)/0.12)] transition-all duration-200 ${
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
            <div className="display text-[15px] font-bold tracking-[0.18em] text-bone">CAIRN</div>
            <div className="mono mt-0.5 text-[9px] text-ash">agent intelligence</div>
          </div>
        )}
      </div>

      <nav className="flex flex-1 flex-col overflow-y-auto p-2">
        {NAVIGATION_GROUPS.map((group) => {
          const items = navItems.filter((item) => item.group === group);
          return (
            <div
              key={group}
              className={
                group === "Utilities" ? "mt-auto border-t border-quartz-vein pt-2" : "mb-2"
              }
            >
              {!collapsed ? (
                <p className="px-2.5 pb-1 pt-1 font-mono text-[9px] uppercase tracking-wider text-ash">
                  {group}
                </p>
              ) : null}
              {items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  aria-label={collapsed ? item.label : undefined}
                  className={({ isActive }) =>
                    `mb-0.5 flex items-center gap-2.5 rounded-sm px-2.5 py-2 text-[13px] font-medium transition-all ${
                      isActive
                        ? "bg-granite/90 text-bone shadow-[inset_2px_0_0_0_var(--copper),0_5px_18px_rgb(var(--overlay-scrim-rgb)/0.12)]"
                        : "text-cinder hover:bg-shale hover:text-bone"
                    } ${collapsed ? "justify-center" : ""}`
                  }
                >
                  <item.icon className="h-4 w-4 shrink-0" strokeWidth={1.8} aria-hidden="true" />
                  {!collapsed && <span className="flex-1">{item.label}</span>}
                  {!collapsed && item.badge !== undefined ? <NavBadge badge={item.badge} /> : null}
                </NavLink>
              ))}
            </div>
          );
        })}
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
        className="mx-3 mb-3 min-h-7 min-w-7 self-end rounded-chip border border-quartz-vein px-1.5 py-0.5 font-mono text-[11px] text-cinder hover:text-bone"
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? "»" : "«"}
      </button>
    </aside>
  );
}
