import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type { PatientDetail } from "../types/api";
import { categoryShort, fmtTime, hoursAgo, ownerLabel } from "../lib/format";
import { BottleneckCard } from "../components/BottleneckCard";
import { NoteWithEvidence } from "../components/NoteWithEvidence";
import { ProtocolTable } from "../components/ProtocolTable";
import { ExtractionPanel } from "../components/ExtractionPanel";
import { WhyStuckPanel } from "../components/WhyStuckPanel";
import { ActionsList } from "../components/ActionsList";
import { UrgencyPill } from "../components/UrgencyPill";

export function PatientPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const [data, setData] = useState<PatientDetail | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = async () => {
    if (!patientId) return;
    setLoading(true);
    try {
      const d = await api.patient(patientId);
      setData(d);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void reload(); }, [patientId]); // eslint-disable-line

  if (loading || !data) {
    return <div className="empty-state">Loading patient…</div>;
  }

  // Combine all evidence spans for the note highlight
  const evSpans = [
    ...data.primary.evidence.map((s) => ({ span: s, level: data.primary.urgency === "red" ? "red" as const : "amber" as const })),
    ...data.secondary.flatMap((b) => b.evidence.map((s) => ({ span: s, level: b.urgency === "red" ? "red" as const : "amber" as const }))),
    ...data.silent_failures.map((sf) => ({ span: sf.trigger_evidence, level: sf.urgency === "red" ? "red" as const : "amber" as const })),
  ];

  return (
    <div className="detail-grid">
      <div className="detail-main">
        <div className="detail-header">
          <div style={{ marginBottom: 6, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>
            <Link to="/dashboard">QUEUE</Link>&nbsp;<span style={{ color: "var(--fg-4)" }}>›</span>&nbsp;PATIENT
          </div>
          <div className="title">
            <span className="pid">{data.id}</span>
            <span className="demog">{data.age}{data.sex} · arrived {fmtTime(data.arrival_time)} ({hoursAgo(data.arrival_time)} ago)</span>
            <div style={{ marginLeft: "auto" }}><UrgencyPill urgency={data.primary.urgency} /></div>
          </div>
          <div className="cc">{data.chief_complaint}</div>
        </div>

        <div className="section">
          <div className="head"><span className="label bright">Bottlenecks</span></div>
          <div className="body">
            <BottleneckCard b={data.primary} isPrimary />
            {data.secondary.map((b, i) => <BottleneckCard key={i} b={b} />)}
          </div>
        </div>

        <div className="section">
          <div className="head">
            <span className="label bright">Patient note (evidence highlighted)</span>
          </div>
          <NoteWithEvidence text={data.note_text} spans={evSpans} />
        </div>

        <div className="section">
          <div className="head"><span className="label bright">Care-pathway evaluation</span></div>
          <div className="body">
            <ProtocolTable matches={data.protocol_matches} />
          </div>
        </div>

        <div className="section">
          <div className="head"><span className="label bright">Workflow actions</span></div>
          <div className="body">
            <ActionsList
              patientId={data.id}
              actions={data.actions}
              primaryBottleneck={data.primary}
              onChange={reload}
            />
          </div>
        </div>
      </div>

      <aside className="detail-side">
        <div className="section">
          <div className="head"><span className="label bright">Why stuck?</span></div>
          <div className="body">
            <WhyStuckPanel patientId={data.id} />
          </div>
        </div>

        <div className="section">
          <div className="head"><span className="label">Snapshot</span></div>
          <div className="body">
            <div className="kv">
              <div className="k">Owner</div><div className="v">{ownerLabel(data.primary.owner)}</div>
              <div className="k">Category</div><div className="v">{categoryShort(data.primary.category)}</div>
              <div className="k">Open SF</div><div className="v">{data.silent_failures.length}</div>
              <div className="k">Open actions</div><div className="v">{data.actions.filter(a => a.status === "open" || a.status === "in_progress").length}</div>
            </div>
          </div>
        </div>

        <div className="section">
          <div className="head"><span className="label">ICD-10 candidates</span></div>
          <div className="body">
            {data.icd_candidates.length === 0 ? (
              <div className="empty-state" style={{ padding: 0, textAlign: "left" }}>none</div>
            ) : (
              <table className="protocol-table">
                <thead>
                  <tr><th>Code</th><th>Description</th><th style={{ textAlign: "right" }}>Score</th></tr>
                </thead>
                <tbody>
                  {data.icd_candidates.map((c) => (
                    <tr key={c.code}>
                      <td><span className="tag code">{c.code}</span></td>
                      <td>{c.description}</td>
                      <td className="dim" style={{ fontFamily: "var(--font-mono)", textAlign: "right" }}>{c.score.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <div className="section">
          <div className="head"><span className="label">Extracted entities</span></div>
          <div className="body">
            <ExtractionPanel ext={data.extraction} />
          </div>
        </div>
      </aside>
    </div>
  );
}
