import type { LabTrend, TrajectorySignal, TrendsPayload } from "../types/api";
import { Sparkline } from "./Sparkline";

const SIGNAL_LABEL: Record<TrajectorySignal, string> = {
  worsening: "Worsening",
  improving: "Improving",
  mixed: "Mixed",
  stable: "Stable",
  none: "No signal",
};

// Trajectory signal -> visual class. Mixed leans on amber (some-better,
// some-worse needs eyes); stable/none stay neutral.
const SIGNAL_CLASS: Record<TrajectorySignal, string> = {
  worsening: "traj-sig-red",
  improving: "traj-sig-green",
  mixed: "traj-sig-amber",
  stable: "traj-sig-neutral",
  none: "traj-sig-neutral",
};

const CLINICAL_CLASS: Record<LabTrend["clinical"], string> = {
  worsening: "traj-red",
  improving: "traj-green",
  stable: "traj-neutral",
  unknown: "traj-neutral",
};

/**
 * Split the lab narrative so a trailing parenthetical verdict — e.g.
 * "lactate 4.1 -> 3.1 -> 2.2 (clearing)" — can be colored by the lab's
 * clinical direction. Everything before the final "(...)" stays neutral mono.
 */
function splitNarrative(narrative: string): { head: string; tail: string | null } {
  const m = narrative.match(/^(.*?)(\s*\([^()]*\))\s*$/);
  if (!m) return { head: narrative, tail: null };
  return { head: m[1].trimEnd(), tail: m[2].trim() };
}

export function TrajectoryPanel({ trends }: { trends: TrendsPayload | null }) {
  // No payload, or a single snapshot with nothing longitudinal to say.
  const hasHistory =
    !!trends &&
    (trends.note_count > 1 ||
      trends.recurrence !== null ||
      trends.resolved_gaps.length > 0);

  if (!trends || !hasHistory) {
    return (
      <div className="section traj-section">
        <div className="head"><span className="label">Trajectory</span></div>
        <div className="body">
          <div className="traj-empty mono small dim">
            Single snapshot — no trend history
          </div>
        </div>
      </div>
    );
  }

  const { labs, recurrence, resolved_gaps, trajectory_signal, note_count } = trends;

  return (
    <div className="section traj-section">
      <div className="head">
        <span className="label bright">Trajectory</span>
        <span className={`traj-sig ${SIGNAL_CLASS[trajectory_signal]}`}>
          {SIGNAL_LABEL[trajectory_signal]}
        </span>
        <span className="tag subtle traj-notecount">
          {note_count} note{note_count === 1 ? "" : "s"}
        </span>
      </div>
      <div className="body traj-body">
        {recurrence && (
          <div className="traj-recurrence">
            <span className="traj-recurrence-badge">Readmit</span>
            <div className="traj-recurrence-text">
              <span className="traj-recurrence-lead">
                {ordinal(recurrence.ordinal)} admission {recurrence.window_phrase}
              </span>
              {recurrence.evidence && (
                <span className="traj-recurrence-ev dim mono small">{recurrence.evidence}</span>
              )}
            </div>
          </div>
        )}

        {labs.length > 0 && (
          <div className="traj-labs">
            {labs.map((lab) => {
              const { head, tail } = splitNarrative(lab.narrative);
              return (
                <div className="traj-lab" key={lab.label}>
                  <span className="traj-lab-name mono">{lab.label}</span>
                  <span className="traj-lab-narr mono">
                    {head}
                    {tail && (
                      <span className={`traj-verdict ${CLINICAL_CLASS[lab.clinical]}`}>
                        {" "}
                        {tail}
                      </span>
                    )}
                  </span>
                  <span className="traj-lab-spark">
                    <Sparkline
                      points={lab.points.map((p) => p.value)}
                      clinical={lab.clinical}
                    />
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {resolved_gaps.length > 0 && (
          <div className="traj-resolved">
            <div className="traj-resolved-head mono">Gaps closed across notes</div>
            <ul className="traj-resolved-list">
              {resolved_gaps.map((g) => (
                <li className="traj-resolved-item" key={`${g.protocol_key}-${g.action_label}-${g.closed_seq}`}>
                  <span className="traj-resolved-glyph" aria-hidden="true">↻</span>
                  <span className="traj-resolved-body">
                    <span className="traj-resolved-action">{g.action_label}</span>
                    <span className="traj-resolved-meta mono small">
                      {g.protocol_name} · was open at note {g.opened_seq}, documented by note {g.closed_seq}
                    </span>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {labs.length === 0 && resolved_gaps.length === 0 && !recurrence && (
          <div className="traj-empty mono small dim">No lab trends extracted across notes.</div>
        )}
      </div>
    </div>
  );
}

function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] ?? s[v] ?? s[0]);
}
