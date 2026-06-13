import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { STORY_STEPS } from "../lib/storyScript";

// =========================================================================
// StoryMode — guided, keyboard-driven demo tour.
// -------------------------------------------------------------------------
// Starts inactive. Begins when something dispatches window "radar:start-story"
// (the titlebar STORY button, the command palette, or the Shift+S shortcut).
//
// While active it renders a fixed bottom bar (mono, dark, 1px top border) with
// step N/total, title, caption, transport controls, and an auto-advance
// play/pause. It drives navigation via react-router useNavigate to each step's
// route, and best-effort outlines a highlightSelector element.
//
// Keyboard while active: →/Space = next, ← = prev, Esc = exit, p = play/pause.
// =========================================================================

const HIGHLIGHT_CLASS = "story-highlight";

export function StoryMode() {
  const navigate = useNavigate();
  const [active, setActive] = useState(false);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);

  const total = STORY_STEPS.length;
  const step = STORY_STEPS[index];

  // Refs so window/keyboard listeners and timers can read current values
  // without re-subscribing on every step change.
  const activeRef = useRef(active);
  const indexRef = useRef(index);
  const playingRef = useRef(playing);
  activeRef.current = active;
  indexRef.current = index;
  playingRef.current = playing;

  const start = useCallback(() => {
    setIndex(0);
    setActive(true);
  }, []);

  const exit = useCallback(() => {
    setActive(false);
    setPlaying(false);
  }, []);

  const next = useCallback(() => {
    setIndex((i) => {
      if (i >= total - 1) {
        // Past the last step → end the tour rather than wrap.
        setActive(false);
        setPlaying(false);
        return i;
      }
      return i + 1;
    });
  }, [total]);

  const prev = useCallback(() => {
    setIndex((i) => Math.max(0, i - 1));
  }, []);

  // Listen for the external start trigger regardless of current state.
  useEffect(() => {
    const onStart = () => start();
    window.addEventListener("radar:start-story", onStart);
    return () => window.removeEventListener("radar:start-story", onStart);
  }, [start]);

  // Navigate whenever the active step changes (and on activation).
  useEffect(() => {
    if (!active || !step) return;
    navigate(step.route);
  }, [active, index, step, navigate]);

  // Best-effort highlight: outline the matched element for this step.
  // Guards nulls; the DOM may not have rendered the target yet, so retry once
  // on a short delay after navigation/paint.
  useEffect(() => {
    if (!active || !step?.highlightSelector) return;
    let el: Element | null = null;
    const clear = () => {
      if (el) el.classList.remove(HIGHLIGHT_CLASS);
      el = null;
    };
    const apply = () => {
      clear();
      try {
        el = document.querySelector(step.highlightSelector as string);
      } catch {
        el = null;
      }
      if (el) {
        el.classList.add(HIGHLIGHT_CLASS);
        el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      }
    };
    // Try after the route's content has had a chance to mount.
    const t1 = window.setTimeout(apply, 120);
    const t2 = window.setTimeout(apply, 520);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      clear();
    };
  }, [active, index, step]);

  // Auto-advance when playing. Uses the current step's durationMs (default 9s).
  useEffect(() => {
    if (!active || !playing || !step) return;
    const dwell = step.durationMs ?? 9000;
    const id = window.setTimeout(() => {
      // If this was the last step, next() will end the tour.
      next();
    }, dwell);
    return () => window.clearTimeout(id);
  }, [active, playing, index, step, next]);

  // Keyboard transport while active.
  useEffect(() => {
    if (!active) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "Escape") {
        e.preventDefault();
        exit();
      } else if (e.key === "ArrowRight" || e.key === " " || e.key === "Spacebar") {
        e.preventDefault();
        next();
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        prev();
      } else if (e.key.toLowerCase() === "p") {
        e.preventDefault();
        setPlaying((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, next, prev, exit]);

  if (!active || !step) return null;

  return (
    <div className="story-bar" role="region" aria-label="Demo tour">
      <div className="story-progress-track" aria-hidden>
        <div
          className="story-progress-fill"
          style={{ width: `${((index + 1) / total) * 100}%` }}
        />
      </div>
      <div className="story-inner">
        <div className="story-count mono">
          {String(index + 1).padStart(2, "0")}
          <span className="story-count-sep">/</span>
          {String(total).padStart(2, "0")}
        </div>
        <div className="story-text">
          <div className="story-title">{step.title}</div>
          <div className="story-caption">{step.caption}</div>
        </div>
        <div className="story-controls">
          <button
            className="story-btn"
            onClick={prev}
            disabled={index === 0}
            title="Previous (←)"
          >
            ← PREV
          </button>
          <button
            className="story-btn"
            onClick={() => setPlaying((v) => !v)}
            title="Play / pause auto-advance (p)"
          >
            {playing ? "❚❚ PAUSE" : "▸ PLAY"}
          </button>
          <button
            className="story-btn story-btn-primary"
            onClick={next}
            title="Next (→ or Space)"
          >
            {index >= total - 1 ? "FINISH" : "NEXT →"}
          </button>
          <button className="story-btn story-btn-exit" onClick={exit} title="Exit (Esc)">
            ESC EXIT
          </button>
        </div>
      </div>
    </div>
  );
}
