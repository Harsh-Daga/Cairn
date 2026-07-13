import { Activity, Lightbulb, Settings, Sparkles, Waves } from "lucide-react";
import { NavLink } from "react-router-dom";
import type { LucideIcon } from "lucide-react";

const items: Array<{ to: string; label: string; icon: LucideIcon; end?: boolean }> = [
  { to: "/", label: "Pulse", icon: Activity, end: true },
  { to: "/sessions", label: "Sessions", icon: Waves },
  { to: "/insights", label: "Insights", icon: Lightbulb },
  { to: "/optimize", label: "Improve", icon: Sparkles },
  { to: "/settings", label: "Settings", icon: Settings },
];

export function MobileDock() {
  return (
    <nav className="mobile-dock" aria-label="Mobile navigation">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) => isActive ? "mobile-dock__item is-active" : "mobile-dock__item"}
        >
          <item.icon className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
          <span>{item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
