// =========================================================================
// Story Mode — guided demo tour script
// -------------------------------------------------------------------------
// An ordered set of steps that drive StoryMode through the product to tell a
// single, tight story for the <4-minute demo video. Captions are written in
// the FDE-demo voice: concrete, operator-first, no hype. They double as the
// narration spine — read them aloud and they hold together as one walkthrough.
//
// This is DATA ONLY. StoryMode.tsx consumes it; nothing here imports React.
// =========================================================================

export interface StoryStep {
  /** Stable id, used for keys and progress tracking. */
  id: string;
  /** react-router path StoryMode navigates to when this step becomes active. */
  route: string;
  /** Short label shown bold in the story bar. */
  title: string;
  /** One or two sentences. The narration line for this beat. */
  caption: string;
  /** Auto-advance dwell time in ms when play is engaged. Optional. */
  durationMs?: number;
  /** Best-effort CSS selector to outline on this step. Optional. */
  highlightSelector?: string;
}

// The patient we drill into. P-1002 is a SNF sepsis presentation
// (fever 39.4, BP 88/52, lactate 3.1) — it carries a lactate-clearing
// trajectory and resolved protocol gaps, so it shows movement, not a static row.
export const STORY_PATIENT_ID = "P-1002";

export const STORY_STEPS: StoryStep[] = [
  {
    id: "queue",
    route: "/dashboard",
    title: "The queue — who is stuck and why",
    caption:
      "Every patient on the floor, ranked by how close they are to a missed step. Not by acuity alone — by where care has actually stalled: an unordered consult, a lab nobody chased, a dispo waiting on a signature.",
    durationMs: 9000,
    highlightSelector: "table.data tbody tr",
  },
  {
    id: "queue-critical",
    route: "/dashboard?urgency=red",
    title: "Filter to critical",
    caption:
      "One filter narrows it to the patients who will get hurt first. The red rows aren't the sickest — they're the ones where the clock is running and the next action is overdue.",
    durationMs: 8000,
    highlightSelector: "table.data",
  },
  {
    id: "patient",
    route: `/p/${STORY_PATIENT_ID}`,
    title: "Drill into P-1002 — septic from a SNF",
    caption:
      "72-year-old from a nursing facility: fever 39.4, pressure 88 over 52, lactate 3.1. The chart reads the note and tells you the single thing blocking this patient, with the line of text it pulled it from.",
    durationMs: 10000,
    highlightSelector: ".bottleneck-card",
  },
  {
    id: "trajectory",
    route: `/p/${STORY_PATIENT_ID}`,
    title: "Trajectory — lactate clearing, gaps resolved",
    caption:
      "This isn't a snapshot. The trajectory panel shows lactate trending down across three notes, creatinine worsening, and the sepsis bundle steps that flipped from open to documented — gaps closed across notes, not silent failures. You can watch the patient get un-stuck.",
    durationMs: 9000,
    highlightSelector: ".traj-section, .traj-labs",
  },
  {
    id: "sandbox",
    route: "/sandbox",
    title: "The engine — paste a note, see the reasoning",
    caption:
      "Drop in any free-text note. Extraction, classification, protocol matching, ICD — every stage timed in milliseconds. No language model sits in the recommendation path. The output is deterministic and you can read why.",
    durationMs: 10000,
    highlightSelector: ".sb-stage, .section",
  },
  {
    id: "capacity",
    route: "/capacity",
    title: "Capacity — the what-if before the page",
    caption:
      "Project census forward and ask the question a charge nurse actually asks: if I expedite these two dispositions, how many beds open and when? Every assumption on the model is named, not hidden.",
    durationMs: 10000,
    highlightSelector: ".section, .anal-card",
  },
  {
    id: "modelcard",
    route: "/analytics",
    title: "The model card — honesty over a clean number",
    caption:
      "On this notional set classification lands at 100 percent, and we say exactly why that's not a victory lap: small labeled sample, the misses it would make, and the conditions under which the number drops. We show our work.",
    durationMs: 10000,
    highlightSelector: ".mc-stats, .mc-honesty",
  },
  {
    id: "analytics",
    route: "/analytics",
    title: "Where the floor bleeds time",
    caption:
      "Aggregate the gaps and the pattern is obvious: which protocols miss most, which owner is carrying the load, where the silent failures cluster. This is the slide that gets a process changed.",
    durationMs: 9000,
    highlightSelector: ".anal-protocols, .anal-grid",
  },
  {
    id: "floor",
    route: "/floor",
    title: "The floor — spatial, live",
    caption:
      "The same signal laid over the physical floor. Run a live tick and the beds pulse as urgency changes in real time: a new critical lights red, a resolved patient fades. The map is the room everyone already pictures.",
    durationMs: 11000,
    highlightSelector: ".wings-grid",
  },
];
