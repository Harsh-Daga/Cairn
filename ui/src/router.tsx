import { lazy, Suspense } from "react";
import { Routes, Route, Navigate } from "react-router-dom";

const OverviewPage = lazy(() =>
  import("./pages/Overview").then((module) => ({ default: module.OverviewPage })),
);
const SessionsPage = lazy(() =>
  import("./pages/Sessions").then((module) => ({ default: module.SessionsPage })),
);
const SessionDetailPage = lazy(() =>
  import("./pages/SessionDetail").then((module) => ({ default: module.SessionDetailPage })),
);
const SessionDiffPage = lazy(() =>
  import("./pages/SessionDiff").then((module) => ({ default: module.SessionDiffPage })),
);
const ContextPage = lazy(() =>
  import("./pages/Context").then((module) => ({ default: module.ContextPage })),
);
const ToolsPage = lazy(() =>
  import("./pages/Tools").then((module) => ({ default: module.ToolsPage })),
);
const FilesPage = lazy(() =>
  import("./pages/Files").then((module) => ({ default: module.FilesPage })),
);
const ComparePage = lazy(() =>
  import("./pages/Compare").then((module) => ({ default: module.ComparePage })),
);
const AgentsPage = lazy(() =>
  import("./pages/Agents").then((module) => ({ default: module.AgentsPage })),
);
const BehaviorPage = lazy(() =>
  import("./pages/Behavior").then((module) => ({ default: module.BehaviorPage })),
);
const QualityPage = lazy(() =>
  import("./pages/Quality").then((module) => ({ default: module.QualityPage })),
);
const InsightsPage = lazy(() =>
  import("./pages/Insights").then((module) => ({ default: module.InsightsPage })),
);
const OptimizePage = lazy(() =>
  import("./pages/Optimize").then((module) => ({ default: module.OptimizePage })),
);
const GuardPage = lazy(() =>
  import("./pages/Guard").then((module) => ({ default: module.GuardPage })),
);
const LivePage = lazy(() =>
  import("./pages/Live").then((module) => ({ default: module.LivePage })),
);
const SearchPage = lazy(() =>
  import("./pages/Search").then((module) => ({ default: module.SearchPage })),
);
const SettingsPage = lazy(() =>
  import("./pages/Settings").then((module) => ({ default: module.SettingsPage })),
);
const RecapPage = lazy(() =>
  import("./pages/Recap").then((module) => ({ default: module.RecapPage })),
);

function RouteFallback() {
  return (
    <div className="card h-48 animate-pulse bg-granite/30 p-6" role="status">
      Loading local view…
    </div>
  );
}

export function AppRouter() {
  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/sessions/diff" element={<SessionDiffPage />} />
        <Route path="/sessions/:id" element={<SessionDetailPage />} />
        <Route path="/context" element={<ContextPage />} />
        <Route path="/tools" element={<ToolsPage />} />
        <Route path="/files" element={<FilesPage />} />
        <Route path="/compare" element={<ComparePage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/behavior" element={<BehaviorPage />} />
        <Route path="/quality" element={<QualityPage />} />
        <Route path="/insights" element={<InsightsPage />} />
        <Route path="/optimize" element={<OptimizePage />} />
        <Route path="/guard" element={<GuardPage />} />
        <Route path="/live" element={<LivePage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/recap" element={<RecapPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
