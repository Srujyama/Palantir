import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import { QueuePage } from "./pages/QueuePage";
import { PatientPage } from "./pages/PatientPage";
import { LandingPage } from "./pages/LandingPage";

function Titlebar() {
  return (
    <header className="titlebar">
      <Link to="/dashboard" className="brand">
        <span className="brand-mark" />
        <span>BOTTLENECK&nbsp;RADAR</span>
      </Link>
      <span className="crumb">
        <span className="sep">/</span>
        <span>Hospital Operations</span>
        <span className="sep">/</span>
        <span>Floor 3 East · Live</span>
      </span>
      <div className="right">
        <Link to="/" style={{ color: "var(--fg-2)" }}>← Landing</Link>
        <span>v0.1 · NOTIONAL DATA</span>
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
        <Route path="/p/:patientId" element={<PatientPage />} />
      </Routes>
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
