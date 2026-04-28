import { useState } from "react";
import { api } from "../lib/api";
import type { ActionItem, Bottleneck } from "../types/api";
import { ownerLabel } from "../lib/format";
import { UrgencyPill } from "./UrgencyPill";

interface Props {
  patientId: string;
  actions: ActionItem[];
  primaryBottleneck: Bottleneck;
  onChange: () => void;
}

export function ActionsList({ patientId, actions, primaryBottleneck, onChange }: Props) {
  const [creating, setCreating] = useState(false);

  const createFromPrimary = async () => {
    setCreating(true);
    try {
      await api.createAction(patientId, {
        title: primaryBottleneck.recommended_action,
        description: primaryBottleneck.rationale,
        owner: primaryBottleneck.owner || "physician",
        urgency: primaryBottleneck.urgency,
        source_category: primaryBottleneck.category,
      });
      onChange();
    } finally {
      setCreating(false);
    }
  };

  const update = async (id: number, status: ActionItem["status"]) => {
    await api.updateAction(id, { status });
    onChange();
  };

  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <button className="btn primary" onClick={createFromPrimary} disabled={creating}>
          {creating ? "CREATING…" : "+ Create action from recommendation"}
        </button>
      </div>
      {actions.length === 0 ? (
        <div className="empty-state" style={{ padding: 24 }}>No actions yet.</div>
      ) : (
        <div className="actions-list">
          {actions.map((a) => (
            <div key={a.id} className="action-row">
              <UrgencyPill urgency={a.urgency} />
              <div>
                <div className="title">{a.title}</div>
                <div className="desc">{a.description}</div>
                <div className="meta" style={{ marginTop: 4 }}>
                  {ownerLabel(a.owner)} · {a.status} · #{a.id}
                </div>
              </div>
              <div className="controls">
                {a.status !== "in_progress" && a.status !== "resolved" && (
                  <button className="btn" onClick={() => update(a.id, "in_progress")}>Start</button>
                )}
                {a.status !== "resolved" && (
                  <button className="btn" onClick={() => update(a.id, "resolved")}>Resolve</button>
                )}
                {a.status !== "escalated" && a.status !== "resolved" && (
                  <button className="btn danger" onClick={() => update(a.id, "escalated")}>Escalate</button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
