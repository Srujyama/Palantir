import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../lib/api";
import type { PatientDetail, PatientInteractions } from "../types/api";
import { categoryShort, fmtTime, hoursAgo, ownerLabel } from "../lib/format";
import { BottleneckCard } from "../components/BottleneckCard";
import { NoteWithEvidence } from "../components/NoteWithEvidence";
import { ProtocolTable } from "../components/ProtocolTable";
import { ExtractionPanel } from "../components/ExtractionPanel";
import { WhyStuckPanel } from "../components/WhyStuckPanel";
import { ActionsList } from "../components/ActionsList";
import { UrgencyPill } from "../components/UrgencyPill";
import { Timeline } from "../components/Timeline";

export function PatientPage() {
  const { patientId } = useParams<{ patientId: string }>();
  const [data, setData] = useState<PatientDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [interactions, setInteractions] = useState<PatientInteractions | null>(null);
  const [interactionsError, setInteractionsError] = useState<string | null>(null);

  // `reload` is keyed to the patient id it was started for: a response that
  // arrives after the user has navigated to a different patient is dropped,
  // so we never paint patient A's chart (or A's interactions) over B.
  const load = (pid: string, isCurrent: () => boolean) => {
    setLoading(true);
    setError(null);
    setData(null);
    setInteractions(null);
    setInteractionsError(null);
    // Fire the interactions check alongside the detail load; a failure here
    // must not block the chart.
    api.interactions(pid)
      .then((ix) => { if (isCurrent()) { setInteractions(ix); setInteractionsError(null); } })
      .catch((err: unknown) => {
        if (isCurrent()) {
          setInteractions(null);
          setInteractionsError(err instanceof Error ? err.message : String(err));
        }
      });
    api.patient(pid)
      .then((d) => { if (isCurrent()) setData(d); })
      .catch((err: unknown) => {
        if (isCurrent()) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => { if (isCurrent()) setLoading(false); });
  };

  useEffect(() => {
    if (!patientId) return;
    let alive = true;
    const isCurrent = () => alive;
    load(patientId, isCurrent);
    // The titlebar LIVE TICK button mutates floor state; refresh in place.
    const onRefresh = () => { if (alive) load(patientId, isCurrent); };
    window.addEventListener("radar:refresh", onRefresh);
    return () => {
      alive = false;
      window.removeEventListener("radar:refresh", onRefresh);
    };
  }, [patientId]); // eslint-disable-line

  const reload = () => {
    if (patientId) load(patientId, () => true);
  };

  if (loading) {
    return <div className="empty-state">Loading patient…</div>;
  }
  if (!data) {
    return (
      <div className="empty-state">
        <div className="error-strip" style={{ display: "inline-flex" }}>
          <span>Patient failed to load{error ? `: ${error}` : ""}</span>
          <button className="btn" onClick={() => void reload()}>Retry</button>
        </div>
      </div>
    );
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
            {data.room && <span className="tag mono" style={{ marginLeft: 8 }}>{data.room}</span>}
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

        {interactions && interactions.flags.length > 0 && (
          <div className="section">
            <div className="head">
              <span className="label bright">Medication interactions</span>
              <span className="tag subtle">{interactions.flags.length} flagged</span>
            </div>
            <div className="body">
              <div className="ix-list">
                {interactions.flags.map((f) => (
                  <div key={f.rule_key} className={`ix-flag ${f.severity}`}>
                    <div className="ix-head">
                      <UrgencyPill urgency={f.severity} />
                      <span className="ix-name">{f.name}</span>
                      <span className="ix-meds">
                        {f.meds_involved.map((m) => (
                          <span key={m.name} className="tag code">{m.name}</span>
                        ))}
                      </span>
                    </div>
                    <div className="ix-rec">{f.recommendation}</div>
                    <div className="dim small mono ix-cite">{f.citation}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        {interactionsError && (
          <div className="section">
            <div className="head"><span className="label">Medication interactions</span></div>
            <div className="body">
              <div className="error-strip">
                <span>Interaction check failed: {interactionsError}</span>
              </div>
            </div>
          </div>
        )}

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

        <div className="section">
          <div className="head"><span className="label bright">Timeline</span></div>
          <div className="body">
            <Timeline patientId={data.id} />
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
