import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

/** Global keyboard shortcuts. Uses the classic two-keystroke "g+X" idiom
 * familiar from Gmail / Linear / GitHub. */
export function KeyboardShortcuts() {
  const navigate = useNavigate();
  const [showHelp, setShowHelp] = useState(false);
  const [pendingG, setPendingG] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "?") {
        e.preventDefault();
        setShowHelp((v) => !v);
        return;
      }
      if (showHelp && e.key === "Escape") {
        setShowHelp(false);
        return;
      }

      if (pendingG) {
        const k = e.key.toLowerCase();
        if (k === "q") navigate("/dashboard");
        else if (k === "f") navigate("/floor");
        else if (k === "a") navigate("/analytics");
        else if (k === "h") navigate("/handoff");
        else if (k === "l") navigate("/");
        setPendingG(false);
        return;
      }

      if (e.key === "g") {
        setPendingG(true);
        setTimeout(() => setPendingG(false), 1500);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, showHelp, pendingG]);

  return (
    <>
      {pendingG && (
        <div className="kb-hint mono">g · waiting · q queue · f floor · a analytics · h handoff · l landing</div>
      )}
      {showHelp && (
        <div className="kb-help-backdrop" onClick={() => setShowHelp(false)}>
          <div className="kb-help" onClick={(e) => e.stopPropagation()}>
            <div className="kb-help-head">
              <h3>Keyboard shortcuts</h3>
              <button className="btn" onClick={() => setShowHelp(false)}>Esc</button>
            </div>
            <div className="kb-help-grid">
              <div className="kb-help-section">
                <h4>Navigation</h4>
                <div className="kb-row"><kbd>g</kbd><kbd>q</kbd><span>Queue</span></div>
                <div className="kb-row"><kbd>g</kbd><kbd>f</kbd><span>Floor map</span></div>
                <div className="kb-row"><kbd>g</kbd><kbd>a</kbd><span>Analytics</span></div>
                <div className="kb-row"><kbd>g</kbd><kbd>h</kbd><span>Handoff report</span></div>
                <div className="kb-row"><kbd>g</kbd><kbd>l</kbd><span>Landing</span></div>
              </div>
              <div className="kb-help-section">
                <h4>Queue</h4>
                <div className="kb-row"><kbd>j</kbd><span>Next row</span></div>
                <div className="kb-row"><kbd>k</kbd><span>Previous row</span></div>
                <div className="kb-row"><kbd>↵</kbd><span>Open patient</span></div>
                <div className="kb-row"><kbd>x</kbd><span>Select for bulk</span></div>
                <div className="kb-row"><kbd>esc</kbd><span>Clear selection</span></div>
              </div>
              <div className="kb-help-section">
                <h4>Global</h4>
                <div className="kb-row"><kbd>⌘</kbd><kbd>K</kbd><span>Command palette</span></div>
                <div className="kb-row"><kbd>?</kbd><span>Toggle this help</span></div>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
