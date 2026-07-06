export interface SavedView {
  id: string;
  name: string;
  params: Record<string, string>;
  pinned?: boolean;
}

const STORAGE_KEY = "cairn.views.v1";

export const DEFAULT_VIEW: SavedView = {
  id: "default",
  name: "Default",
  params: {},
  pinned: true,
};

function readRaw(): SavedView[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [DEFAULT_VIEW];
    const parsed = JSON.parse(raw) as SavedView[];
    if (!Array.isArray(parsed) || parsed.length === 0) return [DEFAULT_VIEW];
    const hasDefault = parsed.some((v) => v.id === "default");
    return hasDefault ? parsed : [DEFAULT_VIEW, ...parsed];
  } catch {
    return [DEFAULT_VIEW];
  }
}

function writeRaw(views: SavedView[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(views));
}

export function loadSavedViews(): SavedView[] {
  return readRaw();
}

export function saveCurrentView(name: string, params: URLSearchParams): SavedView[] {
  const trimmed = name.trim();
  if (!trimmed) return readRaw();
  const entry: SavedView = {
    id: `view-${Date.now()}`,
    name: trimmed,
    params: Object.fromEntries(params.entries()),
  };
  const next = [...readRaw().filter((v) => v.id !== entry.id), entry];
  writeRaw(next);
  return next;
}

export function deleteSavedView(id: string): SavedView[] {
  if (id === "default") return readRaw();
  const next = readRaw().filter((v) => v.id !== id);
  writeRaw(next.length > 0 ? next : [DEFAULT_VIEW]);
  return next.length > 0 ? next : [DEFAULT_VIEW];
}

export function paramsFromView(view: SavedView): URLSearchParams {
  return new URLSearchParams(view.params);
}
