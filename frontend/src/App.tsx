import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Link, Route, Routes, useLocation } from "react-router-dom";
import { QueuePage } from "./pages/QueuePage";
import { PatientPage } from "./pages/PatientPage";
import { LandingPage } from "./pages/LandingPage";
import { FloorPage } from "./pages/FloorPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { HandoffPage } from "./pages/HandoffPage";
import { SandboxPage } from "./pages/SandboxPage";
import { CapacityPage } from "./pages/CapacityPage";
import { CommandPalette } from "./components/CommandPalette";
import { KeyboardShortcuts } from "./components/KeyboardShortcuts";
import { StoryMode } from "./components/StoryMode";
import { NavTabs } from "./components/NavTabs";
import { api } from "./lib/api";

interface HealthState {
  ok: boolean;
  latencyMs: number;
}

function Titlebar() {
  const [health, setHealth] = useState<HealthState | null>(null);
  const [ticking, setTicking] = useState(false);
  const [tickSummary, setTickSummary] = useState<string | null>(null);
  const toastTimer = useRef<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      const start = performance.now();
      try {
        // Race the health probe against a 5s timeout so a hung backend flips
        // the badge red instead of leaving a stale green forever.
        await Promise.race([
          api.health(),
          new Promise((_, reject) =>
            window.setTimeout(() => reject(new Error("health timeout")), 5000),
          ),
        ]);
        const latencyMs = Math.round(performance.now() - start);
        if (!cancelled) setHealth({ ok: true, latencyMs });
      } catch {
        if (!cancelled) setHealth({ ok: false, latencyMs: 0 });
      }
    };
    void check();
    const id = window.setInterval(() => void check(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    };
  }, []);

  const showToast = (text: string) => {
    setTickSummary(text);
    if (toastTimer.current !== null) window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setTickSummary(null), 4000);
  };

  // Guard against concurrent ticks even when fired from different entry points
  // (titlebar button + command palette). A ref reads synchronously; the state
  // flag drives the disabled UI.
  const tickingRef = useRef(false);
  const runTick = async () => {
    if (tickingRef.current) return;
    tickingRef.current = true;
    setTicking(true);
    try {
      const result = await api.simulateTick(60);
      window.dispatchEvent(new CustomEvent("radar:refresh", { detail: result }));
      showToast(
        `+${result.admitted.length} admitted · ${result.discharged.length} discharged · ${result.actions_progressed.length} actions progressed`,
      );
    } catch {
      showToast("Tick failed · API unreachable");
    } finally {
      tickingRef.current = false;
      setTicking(false);
    }
  };

  // The command palette's "Run live tick" action dispatches this so it flows
  // through the same guarded path (in-flight lock + toast) as the button.
  useEffect(() => {
    const onRun = () => void runTick();
    window.addEventListener("radar:run-tick", onRun);
    return () => window.removeEventListener("radar:run-tick", onRun);
  }, []); // eslint-disable-line

  return (
    <header className="titlebar">
      <Link to="/dashboard" className="brand">
        <span className="brand-mark" />
        <span>BOTTLENECK&nbsp;RADAR</span>
      </Link>
      <NavTabs />
      <div className="right">
        <Link to="/" style={{ color: "var(--fg-2)" }}>← Landing</Link>
        <button
          className="kb-hint-pill mono"
          onClick={() => window.dispatchEvent(new CustomEvent("radar:start-story"))}
          title="Guided demo tour (Shift+S)"
          style={{
            cursor: "pointer",
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          ★ STORY
        </button>
        <button
          className="kb-hint-pill mono"
          onClick={() => void runTick()}
          disabled={ticking}
          style={{
            cursor: ticking ? "default" : "pointer",
            opacity: ticking ? 0.5 : 1,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
          }}
        >
          {ticking ? "TICKING…" : "▸ LIVE TICK"}
        </button>
        <span className="kb-hint-pill mono">⌘K</span>
        <span>v0.2 · NOTIONAL DATA</span>
        {health === null && <span style={{ color: "var(--fg-3)" }}>● API —</span>}
        {health !== null && health.ok && (
          <span style={{ color: "var(--signal-green)" }}>
            ● API <span className="mono">{health.latencyMs}ms</span>
          </span>
        )}
        {health !== null && !health.ok && (
          <span style={{ color: "var(--signal-red)" }}>● API DOWN</span>
        )}
      </div>
      {tickSummary && (
        <div
          className="mono"
          style={{
            position: "fixed",
            top: 44,
            left: 0,
            right: 0,
            zIndex: 60,
            padding: "var(--s-2) var(--s-5)",
            background: "var(--signal-blue-bg)",
            borderBottom: "1px solid var(--border-strong)",
            color: "var(--fg-1)",
            fontSize: 11,
            letterSpacing: "0.04em",
          }}
        >
          <span style={{ color: "var(--signal-blue)" }}>TICK</span> · {tickSummary}
        </div>
      )}
    </header>
  );
}

function AppShell() {
  const location = useLocation();
  const isLanding = location.pathname === "/";

  // Shift+S starts the guided demo tour. Chords (g-…), "?" help, and ⌘K are
  // already taken; plain Shift+S is free and is ignored while typing in a
  // field. StoryMode handles its own transport keys once active.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        window.dispatchEvent(new CustomEvent("radar:start-story"));
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
        <Route path="/capacity" element={<CapacityPage />} />
        <Route path="/sandbox" element={<SandboxPage />} />
        <Route path="/p/:patientId" element={<PatientPage />} />
      </Routes>
      <CommandPalette />
      <KeyboardShortcuts />
      <StoryMode />
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
