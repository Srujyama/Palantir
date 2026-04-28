import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { PatientSummary, Stats } from "../types/api";
import { Sidebar } from "../components/Sidebar";
import { KpiStrip } from "../components/KpiStrip";
import { PatientTable } from "../components/PatientTable";

export function QueuePage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [rows, setRows] = useState<PatientSummary[]>([]);
  const [filter, setFilter] = useState<{ urgency?: string; owner?: string; category?: string; search?: string }>({});

  const reload = async () => {
    const [s, p] = await Promise.all([api.stats(), api.patients(filter)]);
    setStats(s);
    setRows(p);
  };

  useEffect(() => { void reload(); /* eslint-disable-line */ }, [JSON.stringify(filter)]);

  return (
    <div className="app-body">
      <Sidebar
        stats={stats}
        filter={{ urgency: filter.urgency, owner: filter.owner, category: filter.category }}
        onFilter={(f) => setFilter(f)}
      />
      <div className="main">
        <KpiStrip stats={stats} />
        <div className="toolbar">
          <input
            className="search-input"
            placeholder="Search patient ID or chief complaint…"
            value={filter.search ?? ""}
            onChange={(e) => setFilter({ ...filter, search: e.target.value })}
          />
          <div className="spacer" />
          <span className="count">{rows.length} ROWS</span>
        </div>
        <PatientTable rows={rows} />
      </div>
    </div>
  );
}
