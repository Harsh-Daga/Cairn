import { Routes, Route, Navigate } from "react-router-dom";
import { OverviewPage } from "./pages/Overview";
import { SessionsPage } from "./pages/Sessions";
import { SessionDetailPage } from "./pages/SessionDetail";
import { SessionDiffPage } from "./pages/SessionDiff";
import { ContextPage } from "./pages/Context";
import { AgentsPage } from "./pages/Agents";
import { BehaviorPage } from "./pages/Behavior";
import { QualityPage } from "./pages/Quality";
import { InsightsPage } from "./pages/Insights";
import { OptimizePage } from "./pages/Optimize";
import { LivePage } from "./pages/Live";
import { SearchPage } from "./pages/Search";
import { SettingsPage } from "./pages/Settings";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/" element={<OverviewPage />} />
      <Route path="/sessions" element={<SessionsPage />} />
      <Route path="/sessions/diff" element={<SessionDiffPage />} />
      <Route path="/sessions/:id" element={<SessionDetailPage />} />
      <Route path="/context" element={<ContextPage />} />
      <Route path="/agents" element={<AgentsPage />} />
      <Route path="/behavior" element={<BehaviorPage />} />
      <Route path="/quality" element={<QualityPage />} />
      <Route path="/insights" element={<InsightsPage />} />
      <Route path="/optimize" element={<OptimizePage />} />
      <Route path="/live" element={<LivePage />} />
      <Route path="/search" element={<SearchPage />} />
      <Route path="/settings" element={<SettingsPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
