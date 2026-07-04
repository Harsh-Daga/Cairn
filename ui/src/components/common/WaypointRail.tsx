import { NavLink } from "react-router-dom";
import { useUiStore } from "@/state/ui";
import { CairnGlyph } from "./CairnGlyph";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  badge?: number | "dot" | "pulse";
}

const NAV_ITEMS: NavItem[] = [
  { to: "/", label: "Overview", icon: "⛰" },
  { to: "/sessions", label: "Sessions", icon: "◎" },
  { to: "/context", label: "Context", icon: "▤" },
  { to: "/agents", label: "Agents", icon: "⬡" },
  { to: "/behavior", label: "Behavior", icon: "〜" },
  { to: "/quality", label: "Quality", icon: "✦" },
  { to: "/insights", label: "Insights", icon: "◈", badge: 0 },
  { to: "/optimize", label: "Optimize", icon: "↻" },
  { to: "/live", label: "Live", icon: "●" },
  { to: "/search", label: "Search", icon: "⌕" },
];

export function WaypointRail() {
  const collapsed = useUiStore((s) => s.railCollapsed);
  const toggleRail = useUiStore((s) => s.toggleRail);

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
        {NAV_ITEMS.map((item) => (
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
            {!collapsed && <span>{item.label}</span>}
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
