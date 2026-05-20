import { useState } from "react";
import { api } from "../lib/api";
import type { ActionEventItem, ActionItem, Bottleneck } from "../types/api";
import { ownerLabel } from "../lib/format";
import { UrgencyPill } from "./UrgencyPill";

interface Props {
  patientId: string;
  actions: ActionItem[];
  primaryBottleneck: Bottleneck;
  onChange: () => void;
}

function fmtEventTime(iso: string): string {
  return new Date(iso).toLocaleString("en-US", {
    month: "short", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
    hour12: false,
  });
}

function EventRow({ ev }: { ev: ActionEventItem }) {
  const change = ev.from_value || ev.to_value
    ? `${ev.from_value ?? "—"} → ${ev.to_value ?? "—"}`
    : "";
  return (
    <div className="ev-row">
      <span className="ev-time mono">{fmtEventTime(ev.created_at)}</span>
      <span className="ev-type mono">{ev.event_type.replace("_", " ")}</span>
      <span className="ev-change mono">{change}</span>
      <span className="ev-actor">{ev.actor}</span>
      {ev.note && <span className="ev-note">· {ev.note}</span>}
    </div>
  );
}

function ActionRow({
  a,
  onUpdate,
}: {
  a: ActionItem;
  onUpdate: (id: number, status: ActionItem["status"]) => Promise<void>;
}) {
  const [audit, setAudit] = useState<ActionEventItem[] | null>(null);
  const [showAudit, setShowAudit] = useState(false);

  const toggleAudit = async () => {
    if (showAudit) {
      setShowAudit(false);
      return;
    }
    setShowAudit(true);
    if (!audit) {
      const evs = await api.actionEvents(a.id);
      setAudit(evs);
    }
  };

  return (
    <div className="action-row">
      <UrgencyPill urgency={a.urgency} />
      <div>
        <div className="title">{a.title}</div>
        <div className="desc">{a.description}</div>
        <div className="meta" style={{ marginTop: 4 }}>
          {ownerLabel(a.owner)} · {a.status} · #{a.id}
        </div>
        {showAudit && (
          <div className="audit-block">
            <div className="audit-head mono">Audit trail · {audit ? audit.length : "…"} events</div>
            {audit ? (
              audit.length === 0
                ? <div className="dim small">No events recorded yet.</div>
                : audit.map((ev) => <EventRow key={ev.id} ev={ev} />)
            ) : (
              <div className="dim small">Loading audit…</div>
            )}
          </div>
        )}
      </div>
      <div className="controls">
        {a.status !== "in_progress" && a.status !== "resolved" && (
          <button className="btn" onClick={() => onUpdate(a.id, "in_progress")}>Start</button>
        )}
        {a.status !== "resolved" && (
          <button className="btn" onClick={() => onUpdate(a.id, "resolved")}>Resolve</button>
        )}
        {a.status !== "escalated" && a.status !== "resolved" && (
          <button className="btn danger" onClick={() => onUpdate(a.id, "escalated")}>Escalate</button>
        )}
        <button className="btn" onClick={toggleAudit}>{showAudit ? "Hide audit" : "Audit"}</button>
      </div>
    </div>
  );
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
            <ActionRow key={a.id} a={a} onUpdate={update} />
          ))}
        </div>
      )}
    </div>
  );
}
