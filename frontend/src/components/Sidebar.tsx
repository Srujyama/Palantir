import type { Stats } from "../types/api";

interface Props {
  stats: Stats | null;
  filter: { urgency?: string; owner?: string; category?: string };
  onFilter: (f: { urgency?: string; owner?: string; category?: string }) => void;
}

const URGENCIES = [
  { key: "red", label: "Critical" },
  { key: "amber", label: "Elevated" },
  { key: "green", label: "Routine" },
];

const CATEGORIES = [
  { key: "missing_soc", label: "Missing SOC" },
  { key: "med_risk", label: "Med risk" },
  { key: "awaiting_consult", label: "Awaiting consult" },
  { key: "awaiting_imaging", label: "Awaiting imaging" },
  { key: "readmit_risk", label: "Readmit risk" },
  { key: "dispo_delay", label: "Dispo delay" },
  { key: "clear", label: "Clear" },
];

const CATEGORY_LABEL_TO_COUNT_KEY: Record<string, string> = {
  missing_soc: "Missing standard-of-care step",
  med_risk: "Medication safety risk",
  awaiting_consult: "Awaiting specialist consult",
  awaiting_imaging: "Awaiting imaging",
  readmit_risk: "High readmission risk",
  dispo_delay: "Discharge / placement delay",
  clear: "No active bottleneck",
};

export function Sidebar({ stats, filter, onFilter }: Props) {
  const urgencyCount = (k: string) => stats?.by_urgency[k] ?? 0;
  const categoryCount = (k: string) =>
    stats?.by_category[CATEGORY_LABEL_TO_COUNT_KEY[k]] ?? 0;

  const ALL_LABEL_COUNT = stats?.total_patients ?? 0;

  return (
    <aside className="sidebar">
      <div className="section-label">Triage</div>
      <div
        className={`nav-item ${!filter.urgency && !filter.category ? "active" : ""}`}
        onClick={() => onFilter({})}
      >
        <span>All patients</span>
        <span className="count">{ALL_LABEL_COUNT}</span>
      </div>
      {URGENCIES.map((u) => (
        <div
          key={u.key}
          className={`nav-item ${filter.urgency === u.key ? "active" : ""}`}
          onClick={() => onFilter({ urgency: u.key })}
        >
          <span>{u.label}</span>
          <span className="count">{urgencyCount(u.key)}</span>
        </div>
      ))}

      <div className="section-label">Bottleneck</div>
      {CATEGORIES.map((c) => (
        <div
          key={c.key}
          className={`nav-item ${filter.category === c.key ? "active" : ""}`}
          onClick={() => onFilter({ category: c.key })}
        >
          <span>{c.label}</span>
          <span className="count">{categoryCount(c.key)}</span>
        </div>
      ))}

      <div className="section-label">Owner</div>
      {[
        { key: "physician", label: "Physician" },
        { key: "nurse", label: "Nurse" },
        { key: "pharmacist", label: "Pharmacist" },
        { key: "case_manager", label: "Case mgmt" },
      ].map((o) => (
        <div
          key={o.key}
          className={`nav-item ${filter.owner === o.key ? "active" : ""}`}
          onClick={() => onFilter({ owner: o.key })}
        >
          <span>{o.label}</span>
          <span className="count">{stats?.by_owner[o.key] ?? 0}</span>
        </div>
      ))}
    </aside>
  );
}
