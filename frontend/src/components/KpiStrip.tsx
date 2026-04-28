import type { Stats } from "../types/api";

export function KpiStrip({ stats }: { stats: Stats | null }) {
  if (!stats) {
    return <div className="kpi-strip" style={{ height: 78 }} />;
  }
  const red = stats.by_urgency.red ?? 0;
  const amber = stats.by_urgency.amber ?? 0;
  const green = stats.by_urgency.green ?? 0;
  const total = stats.total_patients || 1;
  const redPct = Math.round((100 * red) / total);

  return (
    <div className="kpi-strip">
      <div className="kpi">
        <div className="label">In census</div>
        <div className="value">{stats.total_patients}</div>
        <div className="delta">median LOS {stats.median_arrival_age_hours}h</div>
      </div>
      <div className="kpi signal-red">
        <div className="label">Critical</div>
        <div className="value">{red}</div>
        <div className="delta">{redPct}% of census</div>
      </div>
      <div className="kpi signal-amber">
        <div className="label">Elevated</div>
        <div className="value">{amber}</div>
        <div className="delta">awaiting action</div>
      </div>
      <div className="kpi signal-green">
        <div className="label">Routine</div>
        <div className="value">{green}</div>
        <div className="delta">tracking</div>
      </div>
      <div className="kpi">
        <div className="label">Silent failures</div>
        <div className="value">{stats.silent_failures}</div>
        <div className="delta">protocol gaps</div>
      </div>
      <div className="kpi">
        <div className="label">Open actions</div>
        <div className="value">{stats.open_actions}</div>
        <div className="delta">across teams</div>
      </div>
    </div>
  );
}
