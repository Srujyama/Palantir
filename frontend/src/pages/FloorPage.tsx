import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { FloorBed, FloorMap } from "../types/api";
import { categoryShort, ownerLabel } from "../lib/format";

// Transient pulse markers keyed by room. After a live tick refetch we diff the
// new map against the previous urgency-by-room snapshot and tag changed beds:
//   "up"   — became (more) critical, or newly occupied with red  → pulses red
//   "down" — de-escalated or vacated                              → fades
// The class is removed by a timeout so the keyframe runs once and clears.
type PulseKind = "up" | "down";

function bedClass(b: FloorBed, pulse?: PulseKind): string {
  const base = !b.patient_id ? "bed empty" : `bed occupied ${b.urgency ?? ""}`;
  if (!pulse) return base;
  return `${base} floor-pulse floor-pulse-${pulse}`;
}

// Rank urgencies so we can tell escalation (up) from de-escalation (down).
// Empty/no-patient is the lowest rank.
const URGENCY_RANK: Record<string, number> = { green: 1, amber: 2, red: 3 };
function rankOf(b: FloorBed): number {
  if (!b.patient_id || !b.urgency) return 0;
  return URGENCY_RANK[b.urgency] ?? 0;
}

function Legend() {
  return (
    <div className="floor-legend">
      <div className="legend-item"><span className="swatch red" /> Critical</div>
      <div className="legend-item"><span className="swatch amber" /> Elevated</div>
      <div className="legend-item"><span className="swatch green" /> Routine</div>
      <div className="legend-item"><span className="swatch empty" /> Empty bed</div>
    </div>
  );
}

function WingPanel({
  wing,
  beds,
  onHover,
  pulses,
}: {
  wing: string;
  beds: FloorBed[];
  onHover: (b: FloorBed | null) => void;
  pulses: Record<string, PulseKind>;
}) {
  // Lay out beds in two columns: odd beds on the left side of the hallway,
  // even beds on the right. Hospital floor plans actually look like this.
  const left = beds.filter((b) => b.bed_number % 2 === 1);
  const right = beds.filter((b) => b.bed_number % 2 === 0);
  const occupied = beds.filter((b) => b.patient_id).length;
  const red = beds.filter((b) => b.urgency === "red").length;
  const amber = beds.filter((b) => b.urgency === "amber").length;
  return (
    <div className="wing-panel">
      <div className="wing-header">
        <div className="wing-name">{wing} Wing</div>
        <div className="wing-stats">
          <span className="stat">{occupied}/{beds.length} beds</span>
          {red > 0 && <span className="stat red">{red} critical</span>}
          {amber > 0 && <span className="stat amber">{amber} elevated</span>}
        </div>
      </div>
      <div className="hallway">
        <div className="bed-column">
          {left.map((b) => (
            <BedCell key={b.room} bed={b} onHover={onHover} pulse={pulses[b.room]} />
          ))}
        </div>
        <div className="hallway-strip">
          <div className="hallway-label">— hallway —</div>
        </div>
        <div className="bed-column">
          {right.map((b) => (
            <BedCell key={b.room} bed={b} onHover={onHover} pulse={pulses[b.room]} />
          ))}
        </div>
      </div>
    </div>
  );
}

function BedCell({
  bed,
  onHover,
  pulse,
}: {
  bed: FloorBed;
  onHover: (b: FloorBed | null) => void;
  pulse?: PulseKind;
}) {
  const cls = bedClass(bed, pulse);
  if (!bed.patient_id) {
    return (
      <div
        className={cls}
        onMouseEnter={() => onHover(bed)}
        onMouseLeave={() => onHover(null)}
      >
        <div className="bed-room">{bed.room}</div>
        <div className="bed-empty-label">empty</div>
      </div>
    );
  }
  return (
    <Link
      to={`/p/${bed.patient_id}`}
      className={cls}
      onMouseEnter={() => onHover(bed)}
      onMouseLeave={() => onHover(null)}
    >
      <div className="bed-room">{bed.room}</div>
      <div className="bed-pid">{bed.patient_id}</div>
      <div className="bed-demog">{bed.age}{bed.sex}</div>
      {bed.open_actions > 0 && (
        <div className="bed-actions">{bed.open_actions}</div>
      )}
    </Link>
  );
}

export function FloorPage() {
  const [data, setData] = useState<FloorMap | null>(null);
  const [hover, setHover] = useState<FloorBed | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [pulses, setPulses] = useState<Record<string, PulseKind>>({});

  // Previous urgency-by-room snapshot. null until the first successful load so
  // we never pulse the whole floor on initial render — only on real changes.
  const prevRanksRef = useRef<Map<string, number> | null>(null);
  const pulseTimers = useRef<number[]>([]);

  const applyDiff = (next: FloorMap) => {
    const nextRanks = new Map<string, number>();
    for (const b of next.beds) nextRanks.set(b.room, rankOf(b));

    const prev = prevRanksRef.current;
    // First load establishes the baseline silently.
    if (prev !== null) {
      const changed: Record<string, PulseKind> = {};
      for (const b of next.beds) {
        const before = prev.get(b.room) ?? 0;
        const after = nextRanks.get(b.room) ?? 0;
        if (after > before) changed[b.room] = "up";
        else if (after < before) changed[b.room] = "down";
      }
      if (Object.keys(changed).length > 0) {
        // Merge so concurrent ticks don't clobber a still-running pulse.
        setPulses((p) => ({ ...p, ...changed }));
        const rooms = Object.keys(changed);
        // Clear the transient class after the keyframe (~1.2s) has played.
        const t = window.setTimeout(() => {
          setPulses((p) => {
            const copy = { ...p };
            for (const r of rooms) delete copy[r];
            return copy;
          });
        }, 1300);
        pulseTimers.current.push(t);
      }
    }
    prevRanksRef.current = nextRanks;
  };

  const load = async () => {
    try {
      const d = await api.floor();
      applyDiff(d);
      setData(d);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, []);

  // Titlebar live-tick button dispatches "radar:refresh" — refetch the map.
  useEffect(() => {
    const onRefresh = () => { void load(); };
    window.addEventListener("radar:refresh", onRefresh);
    return () => window.removeEventListener("radar:refresh", onRefresh);
  }, []);

  // Flush any in-flight pulse timers on unmount.
  useEffect(() => {
    const timers = pulseTimers.current;
    return () => { for (const t of timers) window.clearTimeout(t); };
  }, []);

  if (!data) {
    if (loading) return <div className="empty-state">Loading floor map…</div>;
    return (
      <div className="floor-page">
        <div className="error-strip">
          <span>Floor map failed to load{error ? `: ${error}` : ""}</span>
          <button className="btn" onClick={() => { setLoading(true); void load(); }}>Retry</button>
        </div>
      </div>
    );
  }

  const occupied = data.beds.filter((b) => b.patient_id).length;
  const red = data.beds.filter((b) => b.urgency === "red").length;
  const amber = data.beds.filter((b) => b.urgency === "amber").length;
  const green = data.beds.filter((b) => b.urgency === "green").length;

  return (
    <div className="floor-page">
      {error && (
        <div className="error-strip" style={{ marginBottom: "var(--s-3)" }}>
          <span>Refresh failed: {error}</span>
          <button className="btn" onClick={() => void load()}>Retry</button>
        </div>
      )}
      <div className="floor-topbar">
        <div className="floor-title">
          <div className="t-eyebrow">Operational Coordination · spatial view</div>
          <h1>Floor Map</h1>
          <div className="t-sub">
            {data.wings.length} wings · {data.beds.length} beds · {occupied} occupied
          </div>
        </div>
        <div className="floor-kpis">
          <div className="fk red"><span className="n">{red}</span><span className="l">Critical</span></div>
          <div className="fk amber"><span className="n">{amber}</span><span className="l">Elevated</span></div>
          <div className="fk green"><span className="n">{green}</span><span className="l">Routine</span></div>
          <div className="fk empty"><span className="n">{data.beds.length - occupied}</span><span className="l">Open beds</span></div>
        </div>
      </div>

      <Legend />

      <div className="wings-grid">
        {data.wings.map((wing) => (
          <WingPanel
            key={wing}
            wing={wing}
            beds={data.beds.filter((b) => b.wing === wing)}
            onHover={setHover}
            pulses={pulses}
          />
        ))}
      </div>

      <div className={`bed-detail ${hover ? "open" : ""}`}>
        {hover && hover.patient_id ? (
          <>
            <div className="bd-head">
              <div className="bd-room">Room {hover.room}</div>
              <div className={`urgency-pill ${hover.urgency ?? ""}`}>
                <span className="dot" /> {hover.urgency?.toUpperCase()}
              </div>
            </div>
            <div className="bd-pid">{hover.patient_id} · {hover.age}{hover.sex}</div>
            <div className="bd-cc">{hover.chief_complaint}</div>
            <div className="bd-kv">
              <span className="k">Category</span>
              <span className="v">{categoryShort(hover.primary_category ?? "")}</span>
              <span className="k">Owner</span>
              <span className="v">{ownerLabel(hover.primary_owner ?? "")}</span>
              <span className="k">Open actions</span>
              <span className="v">{hover.open_actions}</span>
            </div>
            <div className="bd-hint">Click bed to open chart</div>
          </>
        ) : hover ? (
          <>
            <div className="bd-head">
              <div className="bd-room">Room {hover.room}</div>
              <div className="urgency-pill empty">EMPTY</div>
            </div>
            <div className="bd-cc">No patient in this bed.</div>
          </>
        ) : (
          <div className="bd-hint" style={{ textAlign: "center", padding: "32px 0" }}>
            Hover over a bed to inspect the patient
          </div>
        )}
      </div>
    </div>
  );
}
