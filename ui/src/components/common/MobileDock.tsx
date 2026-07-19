import { NavLink } from "react-router-dom";
import { NAVIGATION_ITEMS } from "@/lib/navigation";

export function MobileDock() {
  return (
    <nav className="mobile-dock" aria-label="Mobile navigation">
      {NAVIGATION_ITEMS.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          className={({ isActive }) =>
            isActive ? "mobile-dock__item is-active" : "mobile-dock__item"
          }
        >
          <item.icon className="h-4 w-4" strokeWidth={1.8} aria-hidden="true" />
          <span>{item.shortLabel ?? item.label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
