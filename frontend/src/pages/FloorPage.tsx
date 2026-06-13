import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { FloorBed, FloorMap, Urgency } from "../types/api";
import { categoryShort, ownerLabel } from "../lib/format";

function bedClass(b: FloorBed): string {
  if (!b.patient_id) return "bed empty";
  const u = b.urgency as Urgency | undefined;
  return `bed occupied ${u ?? ""}`;
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

function WingPanel({ wing, beds, onHover }: { wing: string; beds: FloorBed[]; onHover: (b: FloorBed | null) => void }) {
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
            <BedCell key={b.room} bed={b} onHover={onHover} />
          ))}
        </div>
        <div className="hallway-strip">
          <div className="hallway-label">— hallway —</div>
        </div>
        <div className="bed-column">
          {right.map((b) => (
            <BedCell key={b.room} bed={b} onHover={onHover} />
          ))}
        </div>
      </div>
    </div>
  );
}

function BedCell({ bed, onHover }: { bed: FloorBed; onHover: (b: FloorBed | null) => void }) {
  const cls = bedClass(bed);
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

  const load = async () => {
    try {
      const d = await api.floor();
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
