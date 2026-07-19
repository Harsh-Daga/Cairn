import {
  Activity,
  Bot,
  BrainCircuit,
  GitCompareArrows,
  Lightbulb,
  Radar,
  Search,
  Settings,
  Shield,
  SlidersHorizontal,
  Sparkles,
  FileStack,
  Wrench,
  Waves,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

export type NavigationGroup = "Monitor" | "Analyze" | "Act" | "Utilities";

export interface NavigationItem {
  to: string;
  label: string;
  shortLabel?: string;
  group: NavigationGroup;
  icon: LucideIcon;
  end?: boolean;
  shortcut?: "o" | "s" | "l" | "c" | "i";
}

export const NAVIGATION_ITEMS: ReadonlyArray<NavigationItem> = [
  { to: "/", label: "Overview", group: "Monitor", icon: Activity, end: true, shortcut: "o" },
  { to: "/live", label: "Live", group: "Monitor", icon: Activity, shortcut: "l" },
  { to: "/sessions", label: "Sessions", group: "Monitor", icon: Waves, shortcut: "s" },
  { to: "/context", label: "Context", group: "Analyze", icon: SlidersHorizontal, shortcut: "c" },
  { to: "/tools", label: "Tools", group: "Analyze", icon: Wrench },
  { to: "/files", label: "Files", group: "Analyze", icon: FileStack },
  {
    to: "/compare",
    label: "Compare",
    shortLabel: "Compare",
    group: "Analyze",
    icon: GitCompareArrows,
  },
  { to: "/agents", label: "Agents", group: "Analyze", icon: Bot },
  { to: "/behavior", label: "Behavior", group: "Analyze", icon: Radar },
  { to: "/quality", label: "Quality", group: "Analyze", icon: BrainCircuit },
  { to: "/insights", label: "Insights", group: "Act", icon: Lightbulb, shortcut: "i" },
  { to: "/optimize", label: "Optimize", group: "Act", icon: Sparkles },
  { to: "/guard", label: "Guard", group: "Act", icon: Shield },
  { to: "/search", label: "Search", group: "Utilities", icon: Search },
  { to: "/settings", label: "Settings", group: "Utilities", icon: Settings },
];

export const NAVIGATION_GROUPS: ReadonlyArray<NavigationGroup> = [
  "Monitor",
  "Analyze",
  "Act",
  "Utilities",
];

export const PALETTE_ONLY_ROUTES = [{ to: "/recap", label: "Weekly recap" }] as const;

export const GO_SHORTCUTS: ReadonlyMap<string, string> = new Map(
  NAVIGATION_ITEMS.filter((item) => item.shortcut).map((item) => [item.shortcut!, item.to]),
);
