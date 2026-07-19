(function () {
  "use strict";

  var preference = "system";
  try {
    var persisted = JSON.parse(localStorage.getItem("cairn-ui") || "null");
    var state = persisted && typeof persisted === "object" ? persisted.state : null;
    var candidate =
      state && typeof state === "object"
        ? state.themePreference || state.theme || state.colorScheme
        : null;
    if (candidate === "light" || candidate === "dark" || candidate === "system") {
      preference = candidate;
    }
  } catch {
    // Invalid or inaccessible local state safely falls back to the OS preference.
  }

  var resolved =
    preference === "system"
      ? window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light"
      : preference;
  document.documentElement.dataset.themePreference = preference;
  document.documentElement.dataset.theme = resolved;
  document.documentElement.style.colorScheme = resolved;
})();
