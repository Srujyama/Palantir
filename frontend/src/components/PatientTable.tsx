import { useNavigate } from "react-router-dom";
import type { PatientSummary } from "../types/api";
import { categoryShort, hoursAgo, ownerLabel } from "../lib/format";
import { UrgencyPill } from "./UrgencyPill";

interface Props {
  rows: PatientSummary[];
  selectedId?: string;
  selected?: Set<string>;
  onToggleSelect?: (id: string) => void;
  cursor?: number;
}

export function PatientTable({ rows, selectedId, selected, onToggleSelect, cursor }: Props) {
  const navigate = useNavigate();
  const bulkMode = !!onToggleSelect;

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
            {bulkMode && <th style={{ width: 36 }}></th>}
            <th style={{ width: 40 }}>Urg</th>
            <th style={{ width: 90 }}>ID</th>
            <th style={{ width: 64 }}>Room</th>
            <th style={{ width: 60 }}>Age/Sex</th>
            <th style={{ width: 70 }}>LOS</th>
            <th style={{ width: 130 }}>Bottleneck</th>
            <th>Recommended action</th>
            <th style={{ width: 130 }}>Owner</th>
            <th style={{ width: 60, textAlign: "right" }}>SF</th>
            <th style={{ width: 70, textAlign: "right" }}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p, i) => {
            const isSelected = selected?.has(p.id);
            const isCursor = cursor === i;
            const cls = [
              selectedId === p.id ? "selected" : "",
              isSelected ? "bulk-selected" : "",
              isCursor ? "cursor" : "",
            ].join(" ");
            return (
              <tr
                key={p.id}
                className={cls}
                onClick={(e) => {
                  if (bulkMode && (e.metaKey || e.ctrlKey)) {
                    onToggleSelect!(p.id);
                  } else {
                    navigate(`/p/${p.id}`);
                  }
                }}
              >
                {bulkMode && (
                  <td onClick={(e) => { e.stopPropagation(); onToggleSelect!(p.id); }}>
                    <input
                      type="checkbox"
                      checked={!!isSelected}
                      onChange={() => undefined}
                      className="row-check"
                    />
                  </td>
                )}
                <td><UrgencyPill urgency={p.primary_urgency} /></td>
                <td className="mono">{p.id}</td>
                <td className="mono dim">{p.room ?? "—"}</td>
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
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
