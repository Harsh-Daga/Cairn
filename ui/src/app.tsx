import { useEffect } from "react";
import { BrowserRouter, HashRouter } from "react-router-dom";
import { AppRouter } from "./router";
import { Shell } from "./components/common/Shell";
import { ToastProvider } from "./components/common/Toast";
import { isStaticMode } from "./lib/api";
import { watchSystemTheme } from "./lib/theme";
import { useUiStore } from "./state/ui";
import { ErrorBoundary } from "./components/ui";

export default function App() {
  const Router = isStaticMode() ? HashRouter : BrowserRouter;
  const themePreference = useUiStore((state) => state.themePreference);
  useEffect(() => watchSystemTheme(themePreference), [themePreference]);

  return (
    <Router>
      <ToastProvider>
        <Shell>
          <ErrorBoundary>
            <AppRouter />
          </ErrorBoundary>
        </Shell>
      </ToastProvider>
    </Router>
  );
}
