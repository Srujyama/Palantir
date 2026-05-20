import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { PatientTimeline, TimelineEvent } from "../types/api";

function eventClass(e: TimelineEvent): string {
  return `tl-event tl-${e.kind} urg-${e.urgency ?? "none"}`;
}

function symbolFor(kind: TimelineEvent["kind"]): string {
  switch (kind) {
    case "arrival": return "→";
    case "triage": return "Δ";
    case "gap_detected": return "!";
    case "action_created": return "+";
    case "action_state": return "⇒";
    case "note": return "·";
  }
}

function fmt(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString("en-US", {
    weekday: "short",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function Timeline({ patientId }: { patientId: string }) {
  const [data, setData] = useState<PatientTimeline | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const d = await api.timeline(patientId);
        setData(d);
      } finally {
        setLoading(false);
      }
    })();
  }, [patientId]);

  if (loading) return <div className="dim">Loading timeline…</div>;
  if (!data || data.events.length === 0) return <div className="dim">No timeline events.</div>;

  return (
    <div className="tl-list">
      {data.events.map((e, i) => (
        <div key={i} className={eventClass(e)}>
          <div className="tl-rail">
            <span className="tl-glyph">{symbolFor(e.kind)}</span>
          </div>
          <div className="tl-body">
            <div className="tl-head">
              <span className="tl-title">{e.title}</span>
              {e.urgency && (
                <span className={`urgency-pill ${e.urgency}`}><span className="dot" />{e.urgency.toUpperCase()}</span>
              )}
            </div>
            {e.detail && <div className="tl-detail">{e.detail}</div>}
            <div className="tl-meta">
              <span className="tl-time mono">{fmt(e.timestamp)}</span>
              {e.actor && <span className="tl-actor">· {e.actor}</span>}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
