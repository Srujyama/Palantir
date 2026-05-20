import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import { QueuePage } from "./pages/QueuePage";
import { PatientPage } from "./pages/PatientPage";
import { LandingPage } from "./pages/LandingPage";
import { FloorPage } from "./pages/FloorPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { HandoffPage } from "./pages/HandoffPage";
import { CommandPalette } from "./components/CommandPalette";
import { KeyboardShortcuts } from "./components/KeyboardShortcuts";
import { NavTabs } from "./components/NavTabs";

function Titlebar() {
  return (
    <header className="titlebar">
      <Link to="/dashboard" className="brand">
        <span className="brand-mark" />
        <span>BOTTLENECK&nbsp;RADAR</span>
      </Link>
      <NavTabs />
      <div className="right">
        <Link to="/" style={{ color: "var(--fg-2)" }}>← Landing</Link>
        <span className="kb-hint-pill mono">⌘K</span>
        <span>v0.2 · NOTIONAL DATA</span>
        <span style={{ color: "var(--signal-green)" }}>● API CONNECTED</span>
      </div>
    </header>
  );
}

function AppShell() {
  const location = useLocation();
  const isLanding = location.pathname === "/";

  if (isLanding) {
    return (
      <Routes>
        <Route path="/" element={<LandingPage />} />
      </Routes>
    );
  }

  return (
    <div className="app-shell">
      <Titlebar />
      <Routes>
        <Route path="/dashboard" element={<QueuePage />} />
        <Route path="/floor" element={<FloorPage />} />
        <Route path="/analytics" element={<AnalyticsPage />} />
        <Route path="/handoff" element={<HandoffPage />} />
        <Route path="/p/:patientId" element={<PatientPage />} />
      </Routes>
      <CommandPalette />
      <KeyboardShortcuts />
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppShell />
    </BrowserRouter>
  );
}
