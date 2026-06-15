import { Navigate, Route, Routes } from "react-router-dom";
import "./App.css";
import { AppShell } from "./components/AppShell";
import { ProtectedLayout } from "./components/ProtectedLayout";
import { DashboardPage } from "./pages/DashboardPage";
import { VehicleReportPage } from "./pages/VehicleReportPage";
import { ViolationsPage } from "./pages/ViolationsPage";
import { LiveViewPage } from "./pages/LiveViewPage";
import { LoginPage } from "./pages/LoginPage";
import { WatchlistsPage } from "./pages/WatchlistsPage";
import { ChatAssistantPage } from "./pages/ChatAssistantPage";
import { AssistantEnhancePage } from "./pages/AssistantEnhancePage";
import { AssistantEnhanceDebugPage } from "./pages/AssistantEnhanceDebugPage";
import { ChallanEmailPage } from "./pages/ChallanEmailPage";
import { ChallanHistoryPage } from "./pages/ChallanHistoryPage";
import { DailyBriefingPage } from "./pages/DailyBriefingPage";
import { VehicleJourneyPage } from "./pages/VehicleJourneyPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedLayout />}>
        <Route element={<AppShell />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/vehicle-report" element={<VehicleReportPage />} />
          <Route path="/vehicle-journey" element={<VehicleJourneyPage />} />
          <Route path="/violations" element={<ViolationsPage />} />
          <Route path="/violation" element={<ViolationsPage />} />
          <Route path="/live-view" element={<LiveViewPage />} />
          <Route path="/watchlists" element={<WatchlistsPage />} />
          <Route path="/assistant" element={<ChatAssistantPage />} />
          <Route path="/assistant_enhance" element={<AssistantEnhancePage />} />
          <Route path="/assistant_enhance/debug" element={<AssistantEnhanceDebugPage />} />
          <Route path="/challan-email" element={<ChallanEmailPage />} />
          <Route path="/challan-history" element={<ChallanHistoryPage />} />
          <Route path="/daily-briefing" element={<DailyBriefingPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}
