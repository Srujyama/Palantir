import { useNavigate } from "react-router-dom";
import type { PatientSummary } from "../types/api";
import { categoryShort, hoursAgo, ownerLabel } from "../lib/format";
import { UrgencyPill } from "./UrgencyPill";

export function PatientTable({ rows, selectedId }: { rows: PatientSummary[]; selectedId?: string }) {
  const navigate = useNavigate();
  if (rows.length === 0) {
    return (
      <div className="empty-state">
        No patients match the current filters.
      </div>
    );
  }
  return (
    <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th style={{ width: 40 }}>Urg</th>
            <th style={{ width: 90 }}>ID</th>
            <th style={{ width: 60 }}>Age/Sex</th>
            <th style={{ width: 70 }}>LOS</th>
            <th style={{ width: 130 }}>Bottleneck</th>
            <th>Recommended action</th>
            <th style={{ width: 130 }}>Owner</th>
            <th style={{ width: 70, textAlign: "right" }}>SF</th>
            <th style={{ width: 70, textAlign: "right" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr
              key={p.id}
              className={selectedId === p.id ? "selected" : ""}
              onClick={() => navigate(`/p/${p.id}`)}
            >
              <td><UrgencyPill urgency={p.primary_urgency} /></td>
              <td className="mono">{p.id}</td>
              <td className="mono">{p.age}{p.sex}</td>
              <td className="mono">{hoursAgo(p.arrival_time)}</td>
              <td>
                <span className="tag">{categoryShort(p.primary_category)}</span>
              </td>
              <td className="truncate" title={p.primary_action}>{p.primary_action}</td>
              <td>{ownerLabel(p.primary_owner)}</td>
              <td className="mono" style={{ textAlign: "right", color: p.silent_failure_count ? "var(--signal-red)" : "var(--fg-3)" }}>
                {p.silent_failure_count}
              </td>
              <td className="mono" style={{ textAlign: "right" }}>{p.open_actions}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
