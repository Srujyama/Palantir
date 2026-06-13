import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type {
  CapacityForecast,
  CapacitySimulation,
  CensusPoint,
  ModelAssumption,
  WingCapacity,
} from "../types/api";
import { UrgencyPill } from "../components/UrgencyPill";
import { categoryShort, fmtTime } from "../lib/format";
import "../styles/capacity.css";

const CATEGORIES = [
  "missing_soc",
  "med_risk",
  "awaiting_consult",
  "awaiting_imaging",
  "readmit_risk",
  "dispo_delay",
] as const;

const CHECKPOINTS = ["6h", "12h", "24h", "48h"] as const;
const HORIZON = 48;
const SURGE_THRESHOLD = 10;

function signed(n: number): string {
  return n >= 0 ? `+${n}` : `${n}`;
}

function freeAt(series: CensusPoint[], h: number): number | null {
  const pt = series.find((p) => p.hour_offset === h);
  return pt ? pt.projected_free : null;
}

/* ── Census chart: hand-rolled SVG step chart ─────────────────────────── */

function stepPath(
  points: CensusPoint[],
  xOf: (h: number) => number,
  yOf: (v: number) => number,
): string {
  if (points.length === 0) return "";
  let d = `M ${xOf(points[0].hour_offset).toFixed(2)} ${yOf(points[0].projected_free).toFixed(2)}`;
  for (let i = 1; i < points.length; i++) {
    d += ` H ${xOf(points[i].hour_offset).toFixed(2)} V ${yOf(points[i].projected_free).toFixed(2)}`;
  }
  return d;
}

function CensusChart({
  baseline,
  scenario,
}: {
  baseline: CensusPoint[];
  scenario: CensusPoint[] | null;
}) {
  if (baseline.length === 0) {
    return <div className="empty-state">No census series returned by the forecast.</div>;
  }

  const all = scenario ? [...baseline, ...scenario] : baseline;
  const maxFree = Math.max(SURGE_THRESHOLD, ...all.map((p) => p.projected_free));
  const yMax = Math.max(20, Math.ceil(maxFree / 10) * 10);
  const xOf = (h: number) => (h / HORIZON) * 100;
  const yOf = (v: number) => 100 - (v / yMax) * 100;

  const yStep = yMax <= 30 ? 5 : 10;
  const yTicks: number[] = [];
  for (let v = 0; v <= yMax; v += yStep) yTicks.push(v);
  const xTicks: number[] = [];
  for (let h = 0; h <= HORIZON; h += 6) xTicks.push(h);

  return (
    <div className="cap-chart-area">
      <div className="cap-chart-ylabels">
        {yTicks.map((v) => (
          <span key={v} className="mono" style={{ top: `${yOf(v)}%` }}>
            {v}
          </span>
        ))}
      </div>
      <div>
        <div className="cap-plot">
          {/* gridlines as HTML hairlines (crisp dashes, no SVG scaling artifacts) */}
          {yTicks.map((v) => (
            <div
              key={`y${v}`}
              className={`cap-gridline-y ${v === 0 ? "zero" : ""}`}
              style={{ top: `${yOf(v)}%` }}
            />
          ))}
          {xTicks
            .filter((h) => h > 0 && h < HORIZON)
            .map((h) => (
              <div key={`x${h}`} className="cap-gridline-x" style={{ left: `${xOf(h)}%` }} />
            ))}
          <div className="cap-surge-line" style={{ top: `${yOf(SURGE_THRESHOLD)}%` }} />
          <span className="cap-surge-label mono" style={{ top: `${yOf(SURGE_THRESHOLD)}%` }}>
            surge threshold · {SURGE_THRESHOLD}
          </span>
          <svg
            className="cap-svg"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            aria-label="Projected free beds over the next 48 hours"
          >
            <path
              className={`cap-line-base ${scenario ? "dimmed" : ""}`}
              d={stepPath(baseline, xOf, yOf)}
              vectorEffect="non-scaling-stroke"
            />
            {scenario && (
              <path
                className="cap-line-scen"
                d={stepPath(scenario, xOf, yOf)}
                vectorEffect="non-scaling-stroke"
              />
            )}
          </svg>
        </div>
        <div className="cap-chart-xlabels">
          {xTicks.map((h) => (
            <span
              key={h}
              className="mono"
              style={{ left: `${xOf(h)}%` }}
              data-edge={h === 0 ? "start" : h === HORIZON ? "end" : undefined}
            >
              {h === 0 ? "now" : `+${h}h`}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Wings strip ──────────────────────────────────────────────────────── */

function WingCard({ w }: { w: WingCapacity }) {
  const fillColor =
    w.free === 0
      ? "var(--signal-red)"
      : w.free <= 3
        ? "var(--signal-amber)"
        : "var(--signal-blue)";
  return (
    <div className="cap-wing">
      <div className="cap-wing-head">
        <span className="cap-wing-name mono">{w.wing}</span>
        <span className="cap-wing-occ mono">
          {w.occupied}/{w.beds_total}
        </span>
      </div>
      <div className="hbar">
        <div
          className="hbar-fill"
          style={{
            width: `${w.beds_total === 0 ? 0 : Math.round((w.occupied / w.beds_total) * 100)}%`,
            background: fillColor,
          }}
        />
      </div>
      <div className="cap-wing-meta mono">
        <span>
          free <span className="cap-wing-free">{w.free}</span>
        </span>
        <span className="dim">
          24h dc <span className="cap-wing-dc">{w.projected_discharges_24h}</span>
        </span>
      </div>
    </div>
  );
}

/* ── Model assumptions (collapsible) ─────────────────────────────────── */

function AssumptionsSection({ assumptions }: { assumptions: ModelAssumption[] }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="section cap-section cap-assump">
      <button
        type="button"
        className="head cap-assump-toggle"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
      >
        <span className="label bright">Model assumptions</span>
        <span className="cap-assump-hint mono">
          {open ? "hide model assumptions ▾" : `show model assumptions (${assumptions.length}) ▸`}
        </span>
      </button>
      {open && (
        <div className="body cap-assump-body">
          <div className="cap-assump-intro">
            Every number on this page traces to one of the rows below. Deterministic planning
            constants — no ML, no randomness.
          </div>
          {assumptions.map((a) => (
            <div className="cap-assump-row" key={a.key}>
              <div className="cap-assump-label">
                {a.label}
                <span className="cap-assump-key mono">{a.key}</span>
              </div>
              <div>
                <div className="cap-assump-value mono">{a.value}</div>
                <div className="cap-assump-rationale">{a.rationale}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Page ─────────────────────────────────────────────────────────────── */

export function CapacityPage() {
  const [forecast, setForecast] = useState<CapacityForecast | null>(null);
  const [sim, setSim] = useState<CapacitySimulation | null>(null);
  const [catCounts, setCatCounts] = useState<Record<string, number> | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [simError, setSimError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const f = await api.capacityForecast(HORIZON);
      setForecast(f);
      // Probe sim with every category resolved, purely to get honest
      // per-category "movable patient" counts for the builder chips.
      try {
        const probe = await api.capacitySimulate({
          resolve_categories: [...CATEGORIES],
          horizon_hours: HORIZON,
        });
        const counts: Record<string, number> = {};
        probe.freed.forEach((fp) => {
          counts[fp.category] = (counts[fp.category] ?? 0) + 1;
        });
        setCatCounts(counts);
      } catch {
        // Counts are a nicety; the builder still works without them.
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
    // LIVE TICK changes the census; re-pull the baseline forecast in place.
    const onRefresh = () => void load();
    window.addEventListener("radar:refresh", onRefresh);
    return () => window.removeEventListener("radar:refresh", onRefresh);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleCat = (cat: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(cat)) next.delete(cat);
      else next.add(cat);
      return next;
    });
  };

  const runScenario = async () => {
    if (selected.size === 0 || running) return;
    setRunning(true);
    setSimError(null);
    try {
      const s = await api.capacitySimulate({
        resolve_categories: Array.from(selected),
        horizon_hours: HORIZON,
      });
      setSim(s);
    } catch (e) {
      setSimError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  };

  const resetScenario = () => {
    setSim(null);
    setSimError(null);
    setSelected(new Set());
  };

  if (loading) {
    return <div className="empty-state">Loading capacity forecast…</div>;
  }

  if (error) {
    return (
      <div className="cap-page">
        <div className="cap-error">
          <div className="cap-error-title mono">CAPACITY FORECAST UNAVAILABLE</div>
          <div className="cap-error-msg mono">{error}</div>
          <button className="btn primary" onClick={() => void load()}>
            Retry
          </button>
        </div>
      </div>
    );
  }

  if (!forecast || forecast.series.length === 0) {
    return (
      <div className="cap-page">
        <div className="empty-state">No forecast data — the floor appears to be empty.</div>
      </div>
    );
  }

  const baseline = sim ? sim.baseline : forecast.series;
  const scenario = sim ? sim.scenario : null;
  const freeNow = freeAt(baseline, 0) ?? forecast.beds_total - forecast.census_now;
  const base24 = freeAt(baseline, 24);
  const base48 = freeAt(baseline, 48);
  const scen24 = scenario ? freeAt(scenario, 24) : null;
  const scen48 = scenario ? freeAt(scenario, 48) : null;
  const d24 = sim ? (sim.delta_free_beds["24h"] ?? 0) : 0;

  const freeNowSignal =
    freeNow <= SURGE_THRESHOLD ? "signal-red" : freeNow <= 20 ? "signal-amber" : "signal-green";

  return (
    <div className="cap-page">
      <div className="cap-topbar">
        <div className="t-eyebrow">Operational Decisions · bed capacity</div>
        <h1>Capacity / What-If</h1>
        <div className="t-sub">
          48-hour bed-census forecast over {forecast.beds_total} beds, plus a scenario builder:
          resolve a bottleneck group and see how many beds free up, by when. Anchor{" "}
          <span className="mono">{fmtTime(forecast.anchor)}</span> · deterministic model, every
          number traces to a stated assumption.
        </div>
      </div>

      <div className="kpi-strip cap-kpis">
        <div className="kpi">
          <span className="label">Census now</span>
          <span className="value">{forecast.census_now}</span>
          <span className="delta">of {forecast.beds_total} beds</span>
        </div>
        <div className={`kpi ${freeNowSignal}`}>
          <span className="label">Beds free now</span>
          <span className="value">{freeNow}</span>
          <span className="delta">surge threshold {SURGE_THRESHOLD}</span>
        </div>
        <div className={`kpi ${sim && d24 > 0 ? "signal-green" : ""}`}>
          <span className="label">Proj. free at 24h</span>
          <span className="value">{scen24 ?? base24 ?? "—"}</span>
          <span className="delta">
            {sim && scen24 !== null && base24 !== null
              ? `${signed(scen24 - base24)} vs baseline ${base24}`
              : "baseline"}
          </span>
        </div>
        <div className={`kpi ${sim && (sim.delta_free_beds["48h"] ?? 0) > 0 ? "signal-green" : ""}`}>
          <span className="label">Proj. free at 48h</span>
          <span className="value">{scen48 ?? base48 ?? "—"}</span>
          <span className="delta">
            {sim && scen48 !== null && base48 !== null
              ? `${signed(scen48 - base48)} vs baseline ${base48}`
              : "baseline"}
          </span>
        </div>
      </div>

      <div className="cap-layout">
        {/* ── Left rail: scenario builder + delta readout ── */}
        <div className="cap-rail">
          <div className="cap-card">
            <div className="cap-card-head">
              <span className="cap-microlabel">Scenario builder</span>
            </div>
            <div className="cap-card-body">
              <div className="cap-builder-hint">
                Toggle the bottleneck groups you could resolve, then run. Counts are patients
                whose projected discharge moves.
              </div>
              <div className="cap-chips">
                {CATEGORIES.map((cat) => (
                  <button
                    type="button"
                    key={cat}
                    className={`cap-chip ${selected.has(cat) ? "on" : ""}`}
                    onClick={() => toggleCat(cat)}
                    aria-pressed={selected.has(cat)}
                  >
                    <span className="cap-chip-box" aria-hidden="true" />
                    <span className="cap-chip-label">{categoryShort(cat)}</span>
                    <span className="cap-chip-count mono">
                      {catCounts ? (catCounts[cat] ?? 0) : "·"}
                    </span>
                  </button>
                ))}
              </div>
              <div className="cap-run-row">
                <button
                  className="btn primary"
                  disabled={selected.size === 0 || running}
                  onClick={() => void runScenario()}
                >
                  {running ? "Running…" : "Run scenario"}
                </button>
                {(sim !== null || selected.size > 0) && (
                  <button className="btn" onClick={resetScenario} disabled={running}>
                    Reset
                  </button>
                )}
              </div>
              {simError && <div className="cap-sim-error mono">scenario failed: {simError}</div>}
            </div>
          </div>

          <div className="cap-card">
            <div className="cap-card-head">
              <span className="cap-microlabel">Scenario impact</span>
            </div>
            {sim ? (
              <div className="cap-card-body">
                <div className="cap-delta-big mono">
                  <span className={d24 > 0 ? "pos" : "flat"}>{signed(d24)}</span> beds{" "}
                  <span className="dim">by 24h</span>
                </div>
                <div className="cap-delta-grid">
                  {CHECKPOINTS.map((cp) => {
                    const v = sim.delta_free_beds[cp] ?? 0;
                    return (
                      <div className="cap-delta-cell" key={cp}>
                        <span className="cap-delta-cp mono">+{cp}</span>
                        <span className={`cap-delta-val mono ${v > 0 ? "pos" : "flat"}`}>
                          {signed(v)}
                        </span>
                      </div>
                    );
                  })}
                </div>
                <div className="cap-delta-note">
                  {sim.freed.length === 0
                    ? "No discharges move under this scenario."
                    : `${sim.freed.length} patient${sim.freed.length === 1 ? "" : "s"} discharge earlier under this scenario.`}
                </div>
              </div>
            ) : (
              <div className="empty-state cap-empty-tight">
                No scenario yet. Toggle bottleneck groups and run.
              </div>
            )}
          </div>
        </div>

        {/* ── Census chart ── */}
        <div className="cap-card cap-chart-card">
          <div className="cap-card-head">
            <span className="cap-microlabel">Projected free beds · next 48h</span>
            <span className="cap-legend">
              <span className="cap-legend-item">
                <span className={`cap-legend-swatch base ${scenario ? "dimmed" : ""}`} /> baseline
              </span>
              {scenario && (
                <span className="cap-legend-item">
                  <span className="cap-legend-swatch scen" /> scenario
                </span>
              )}
            </span>
          </div>
          <div className="cap-card-body">
            <CensusChart baseline={baseline} scenario={scenario} />
          </div>
        </div>
      </div>

      {/* ── Freed patients ── */}
      {sim && (
        <div className="section cap-section">
          <div className="head">
            <span className="label bright">Freed patients</span>
            <span className="cap-head-count mono">{sim.freed.length} move earlier</span>
          </div>
          {sim.freed.length === 0 ? (
            <div className="empty-state">
              No patients move under this scenario — the selected groups have no resolvable wait.
            </div>
          ) : (
            <table className="data cap-freed-table">
              <thead>
                <tr>
                  <th>Patient</th>
                  <th>Room</th>
                  <th>Category</th>
                  <th>Urgency</th>
                  <th>Discharge ETA</th>
                  <th>Gained</th>
                </tr>
              </thead>
              <tbody>
                {sim.freed.map((f) => (
                  <tr key={f.patient_id}>
                    <td className="mono">
                      <Link to={`/p/${f.patient_id}`}>{f.patient_id}</Link>
                    </td>
                    <td className="mono">{f.room ?? "—"}</td>
                    <td>
                      <span className="tag subtle">{categoryShort(f.category)}</span>
                    </td>
                    <td>
                      <UrgencyPill urgency={f.urgency} />
                    </td>
                    <td className="mono">
                      <span className="dim">+{f.baseline_eta_hours}h</span>
                      <span className="cap-eta-arrow"> → </span>
                      <span className="cap-eta-scen">+{f.scenario_eta_hours}h</span>
                    </td>
                    <td className="mono cap-gained">{f.gained_hours}h</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* ── Wings strip ── */}
      <div className="section cap-section">
        <div className="head">
          <span className="label bright">Wings</span>
          <span className="cap-head-count mono">occupancy + projected 24h discharges</span>
        </div>
        <div className="body">
          {forecast.wings.length === 0 ? (
            <div className="empty-state">No wing data.</div>
          ) : (
            <div className="cap-wings">
              {forecast.wings.map((w) => (
                <WingCard key={w.wing} w={w} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Model assumptions ── */}
      <AssumptionsSection assumptions={sim ? sim.assumptions : forecast.assumptions} />
    </div>
  );
}
