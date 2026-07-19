export const THEME_PREFERENCES = ["system", "light", "dark"] as const;

export type ThemePreference = (typeof THEME_PREFERENCES)[number];
export type ResolvedTheme = Exclude<ThemePreference, "system">;

const SYSTEM_DARK_QUERY = "(prefers-color-scheme: dark)";

export function normalizeThemePreference(value: unknown): ThemePreference {
  return typeof value === "string" && (THEME_PREFERENCES as readonly string[]).includes(value)
    ? (value as ThemePreference)
    : "system";
}

export function resolveThemePreference(
  preference: ThemePreference,
  systemDark = window.matchMedia(SYSTEM_DARK_QUERY).matches,
): ResolvedTheme {
  return preference === "system" ? (systemDark ? "dark" : "light") : preference;
}

export function applyThemePreference(preference: ThemePreference): ResolvedTheme {
  const resolved = resolveThemePreference(preference);
  const root = document.documentElement;
  root.dataset.themePreference = preference;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  return resolved;
}

export function watchSystemTheme(
  preference: ThemePreference,
  apply = applyThemePreference,
): () => void {
  apply(preference);
  if (preference !== "system") return () => undefined;

  const media = window.matchMedia(SYSTEM_DARK_QUERY);
  const update = () => apply("system");
  media.addEventListener("change", update);
  return () => media.removeEventListener("change", update);
}
