import { beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  applyThemePreference,
  normalizeThemePreference,
  resolveThemePreference,
  watchSystemTheme,
} from "@/lib/theme";
import { migrateUiState, useUiStore } from "@/state/ui";

const root = join(dirname(fileURLToPath(import.meta.url)), "../..");
const bootstrap = readFileSync(join(root, "public/theme-bootstrap.js"), "utf-8");
const indexHtml = readFileSync(join(root, "index.html"), "utf-8");
const themeCss = readFileSync(join(root, "src/theme.css"), "utf-8");

type Rgb = readonly [number, number, number];

function rgbToken(block: string, token: string): Rgb {
  const match = block.match(new RegExp(`--${token}-rgb:\\s*(\\d+)\\s+(\\d+)\\s+(\\d+)`));
  if (!match) throw new Error(`missing ${token} in theme block`);
  return [Number(match[1]), Number(match[2]), Number(match[3])];
}

function luminance(rgb: Rgb): number {
  const linear = (channel: number) => {
    const normalized = channel / 255;
    return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
  };
  const red = linear(rgb[0]);
  const green = linear(rgb[1]);
  const blue = linear(rgb[2]);
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrast(first: Rgb, second: Rgb): number {
  const lighter = Math.max(luminance(first), luminance(second));
  const darker = Math.min(luminance(first), luminance(second));
  return (lighter + 0.05) / (darker + 0.05);
}

function sourceFiles(path: string): string[] {
  return readdirSync(path, { withFileTypes: true }).flatMap((entry) => {
    const child = join(path, entry.name);
    return entry.isDirectory()
      ? sourceFiles(child)
      : /\.(?:ts|tsx)$/.test(entry.name)
        ? [child]
        : [];
  });
}

function mockColorScheme(dark: boolean) {
  const listeners = new Set<() => void>();
  Object.defineProperty(window, "matchMedia", {
    configurable: true,
    value: vi.fn(() => ({
      matches: dark,
      media: "(prefers-color-scheme: dark)",
      onchange: null,
      addEventListener: (_event: string, listener: () => void) => listeners.add(listener),
      removeEventListener: (_event: string, listener: () => void) => listeners.delete(listener),
      addListener: () => undefined,
      removeListener: () => undefined,
      dispatchEvent: () => true,
    })),
  });
  return listeners;
}

function runBootstrap() {
  Function(bootstrap)();
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
  document.documentElement.removeAttribute("data-theme-preference");
  document.documentElement.removeAttribute("style");
  mockColorScheme(false);
});

describe("theme preference contract", () => {
  it("normalizes invalid state and resolves the system theme", () => {
    expect(normalizeThemePreference("dark")).toBe("dark");
    expect(normalizeThemePreference("sepia")).toBe("system");
    expect(resolveThemePreference("system", true)).toBe("dark");
    expect(resolveThemePreference("system", false)).toBe("light");
  });

  it("applies explicit and system themes to the root element", () => {
    expect(applyThemePreference("dark")).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.dataset.themePreference).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");
  });

  it("watches OS changes only for a system preference", () => {
    const listeners = mockColorScheme(false);
    const apply = vi.fn();
    const dispose = watchSystemTheme("system", apply);
    expect(apply).toHaveBeenCalledWith("system");
    expect(listeners.size).toBe(1);
    listeners.forEach((listener) => listener());
    expect(apply).toHaveBeenCalledTimes(2);
    dispose();
    expect(listeners.size).toBe(0);
  });

  it("migrates legacy theme fields without discarding existing state", () => {
    const migrated = migrateUiState({ railCollapsed: true, theme: "light" });
    expect(migrated.railCollapsed).toBe(true);
    expect(migrated.themePreference).toBe("light");
    expect(migrateUiState({ colorScheme: "invalid" }).themePreference).toBe("system");
  });

  it("persists an explicit preference through the UI store", () => {
    useUiStore.getState().setThemePreference("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    const persisted = JSON.parse(localStorage.getItem("cairn-ui") ?? "{}");
    expect(persisted.state.themePreference).toBe("light");
  });

  it("defines AA text and control contrast in both palettes", () => {
    const dark = themeCss.slice(
      themeCss.indexOf(":root {"),
      themeCss.indexOf(':root[data-theme="light"]'),
    );
    const light = themeCss.slice(themeCss.indexOf(':root[data-theme="light"]'));
    for (const block of [dark, light]) {
      const canvas = rgbToken(block, "surface-canvas");
      const base = rgbToken(block, "surface-base");
      expect(contrast(rgbToken(block, "text-primary"), canvas)).toBeGreaterThanOrEqual(7);
      expect(contrast(rgbToken(block, "text-muted"), canvas)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(rgbToken(block, "text-disabled"), canvas)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(rgbToken(block, "accent-primary"), base)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(rgbToken(block, "focus"), canvas)).toBeGreaterThanOrEqual(3);
      for (const severity of [
        "severity-info",
        "severity-warning",
        "severity-high",
        "severity-critical",
      ]) {
        expect(contrast(rgbToken(block, severity), base), severity).toBeGreaterThanOrEqual(4.5);
      }
    }
  });

  it("keeps hard-coded colors out of component source", () => {
    const offenders = sourceFiles(join(root, "src"))
      .filter((path) => !path.endsWith("theme.test.ts"))
      .filter((path) => /#[0-9a-f]{3,8}\b/i.test(readFileSync(path, "utf-8")));
    expect(offenders).toEqual([]);
  });
});

describe("pre-mount bootstrap", () => {
  it("runs before the React module and uses a same-origin external script", () => {
    const bootstrapPosition = indexHtml.indexOf('<script src="/theme-bootstrap.js"></script>');
    const reactPosition = indexHtml.indexOf('<script type="module" src="/src/main.tsx"></script>');
    expect(bootstrapPosition).toBeGreaterThan(0);
    expect(bootstrapPosition).toBeLessThan(reactPosition);
    expect(indexHtml).not.toContain("unsafe-inline");
  });

  it("reads the current and legacy persisted formats before React mounts", () => {
    localStorage.setItem("cairn-ui", JSON.stringify({ state: { theme: "dark" } }));
    runBootstrap();
    expect(document.documentElement.dataset.themePreference).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");

    localStorage.setItem("cairn-ui", "{not-json");
    mockColorScheme(false);
    runBootstrap();
    expect(document.documentElement.dataset.themePreference).toBe("system");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
