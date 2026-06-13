import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { HandoffReport, HandoffSection, HandoffSnapshotMeta } from "../types/api";
import { ownerLabel } from "../lib/format";

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function hhmm(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function Section({ s }: { s: HandoffSection }) {
  return (
    <div className={`ho-section urg-${s.urgency ?? "none"}`}>
      <div className="ho-section-head">
        <div className="ho-section-title">{s.title}</div>
        <div className="ho-section-tags">
          {s.room && <span className="tag mono">{s.room}</span>}
          {s.urgency && (
            <span className={`urgency-pill ${s.urgency}`}><span className="dot" />{s.urgency.toUpperCase()}</span>
          )}
          {s.patient_id && (
            <Link to={`/p/${s.patient_id}`} className="tag mono code">{s.patient_id}</Link>
          )}
        </div>
      </div>
      <ul className="ho-bullets">
        {s.bullets.map((b, i) => (
          <li key={i}>{b}</li>
        ))}
      </ul>
    </div>
  );
}

function Block({
  num,
  title,
  subtitle,
  count,
  sections,
}: {
  num: string;
  title: string;
  subtitle?: string;
  count: number;
  sections: HandoffSection[];
}) {
  return (
    <div className="ho-block">
      <div className="ho-block-head">
        <div className="ho-num">{num}</div>
        <div className="ho-block-title">
          <h2>{title}</h2>
          {subtitle && <div className="ho-block-sub">{subtitle}</div>}
        </div>
        <div className="ho-count mono">{count}</div>
      </div>
      <div className="ho-sections">
        {sections.length === 0 ? (
          <div className="ho-empty">Nothing on the board for this section.</div>
        ) : (
          sections.map((s, i) => <Section key={i} s={s} />)
        )}
      </div>
    </div>
  );
}

function ReportBody({ data }: { data: HandoffReport }) {
  return (
    <>
      <div className="ho-header">
        <div>
          <div className="ho-eyebrow">Operational coordination · shift change artifact</div>
          <h1 className="ho-title">Bottleneck Radar — Shift Handoff</h1>
          <div className="ho-sub">
            {data.shift_label} · {data.floor}
          </div>
        </div>
        <div className="ho-summary">
          <div className="ho-summary-item">
            <span className="n mono">{data.summary.total_patients}</span>
            <span className="l">Patients</span>
          </div>
          <div className="ho-summary-item red">
            <span className="n mono">{data.summary.critical}</span>
            <span className="l">Critical</span>
          </div>
          <div className="ho-summary-item amber">
            <span className="n mono">{data.summary.open_gaps}</span>
            <span className="l">Open gaps</span>
          </div>
          <div className="ho-summary-item">
            <span className="n mono">{data.summary.open_actions}</span>
            <span className="l">Open actions</span>
          </div>
          <div className="ho-summary-item">
            <span className="n mono">{data.summary.dispo_holds}</span>
            <span className="l">Dispo holds</span>
          </div>
        </div>
      </div>

      <Block
        num="01"
        title="Critical patients"
        subtitle="Patients whose primary bottleneck is red. Touch first."
        count={data.critical.length}
        sections={data.critical}
      />

      <Block
        num="02"
        title="Open protocol gaps"
        subtitle="Documented care-pathway steps that are missing from the chart, grouped by patient."
        count={data.open_protocol_gaps.length}
        sections={data.open_protocol_gaps}
      />

      <Block
        num="03"
        title="Patients awaiting disposition"
        subtitle="Medically optimized but blocked. Case management own list."
        count={data.awaiting_dispo.length}
        sections={data.awaiting_dispo}
      />

      {Object.entries(data.open_actions_by_owner).length > 0 && (
        <div className="ho-block">
          <div className="ho-block-head">
            <div className="ho-num">04</div>
            <div className="ho-block-title">
              <h2>Open coordination tasks, by owner</h2>
              <div className="ho-block-sub">Routed work that hasn't closed yet.</div>
            </div>
            <div className="ho-count mono">
              {Object.values(data.open_actions_by_owner).flat().length}
            </div>
          </div>
          <div className="ho-owners">
            {Object.entries(data.open_actions_by_owner).map(([owner, sections]) => (
              <div key={owner} className="ho-owner-block">
                <h3 className="ho-owner-name">{ownerLabel(owner)}</h3>
                <div className="ho-sections">
                  {sections.map((s, i) => <Section key={i} s={s} />)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="ho-foot">
        Operational coordination tool — not a clinical decision aid. All cases notional.
        No PHI. Generated {new Date(data.generated_at).toLocaleString()}.
      </div>
    </>
  );
}

export function HandoffPage() {
  const [data, setData] = useState<HandoffReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Finalized-snapshot history + the currently-viewed frozen artifact.
  const [history, setHistory] = useState<HandoffSnapshotMeta[]>([]);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [frozen, setFrozen] = useState<HandoffReport | null>(null);
  const [frozenMeta, setFrozenMeta] = useState<HandoffSnapshotMeta | null>(null);
  const [frozenError, setFrozenError] = useState<string | null>(null);
  const [finalizing, setFinalizing] = useState(false);
  const [finalizeMsg, setFinalizeMsg] = useState<string | null>(null);
  const [finalizeError, setFinalizeError] = useState<string | null>(null);

  const loadHistory = () => {
    void api.handoffHistory()
      .then((h) => {
        setHistory(h.snapshots);
        setHistoryError(null);
      })
      .catch((err: unknown) => setHistoryError(errMsg(err)));
  };

  useEffect(() => {
    const load = () => {
      void (async () => {
        try {
          const d = await api.handoff();
          setData(d);
          setError(null);
        } catch (err) {
          setError(errMsg(err));
        } finally {
          setLoading(false);
        }
      })();
    };
    load();
    loadHistory();
    // LIVE TICK changes who is on the floor; rebuild the handoff in place.
    const onRefresh = () => {
      load();
      loadHistory();
    };
    window.addEventListener("radar:refresh", onRefresh);
    return () => window.removeEventListener("radar:refresh", onRefresh);
  }, []);

  const finalize = async () => {
    setFinalizing(true);
    setFinalizeError(null);
    try {
      const meta = await api.finalizeHandoff();
      setFinalizeMsg(`Frozen at ${hhmm(meta.captured_at)}`);
      loadHistory();
    } catch (err) {
      setFinalizeError(errMsg(err));
    } finally {
      setFinalizing(false);
    }
  };

  const openSnapshot = async (id: number, meta: HandoffSnapshotMeta) => {
    setFrozenError(null);
    setFrozenMeta(meta);
    try {
      const report = await api.handoffSnapshot(id);
      setFrozen(report);
    } catch (err) {
      setFrozen(null);
      setFrozenError(errMsg(err));
    }
  };

  const backToLive = () => {
    setFrozen(null);
    setFrozenMeta(null);
    setFrozenError(null);
  };

  if (loading) return <div className="empty-state">Building handoff report…</div>;
  if (!data) {
    return (
      <div className="empty-state">
        <div className="error-strip" style={{ display: "inline-flex" }}>
          <span>Handoff failed to load{error ? `: ${error}` : ""}</span>
        </div>
      </div>
    );
  }

  const viewing = frozen ?? data;

  return (
    <div className="ho-page">
      <div className="ho-paper">
        {/* Controls + history live above the artifact and never print. */}
        <div className="ho-controls no-print">
          <div className="ho-controls-row">
            <button
              className="btn primary"
              onClick={() => void finalize()}
              disabled={finalizing}
            >
              {finalizing ? "Finalizing…" : "Finalize this handoff"}
            </button>
            <button className="btn" onClick={() => window.print()}>Print this report</button>
            {finalizeMsg && <span className="ho-finalize-msg mono">{finalizeMsg}</span>}
          </div>
          {finalizeError && (
            <div className="error-strip">
              <span>Finalize failed: {finalizeError}</span>
            </div>
          )}

          <div className="ho-history">
            <div className="ho-history-head">Past handoffs</div>
            {historyError ? (
              <div className="error-strip">
                <span>History failed to load: {historyError}</span>
              </div>
            ) : history.length === 0 ? (
              <div className="ho-empty">No finalized handoffs yet — finalize one to freeze the board.</div>
            ) : (
              <div className="ho-history-list">
                {history.map((h) => (
                  <button
                    key={h.id}
                    type="button"
                    className={`ho-history-row${frozenMeta?.id === h.id ? " active" : ""}`}
                    onClick={() => void openSnapshot(h.id, h)}
                  >
                    <span className="ho-history-shift">{h.shift_label}</span>
                    <span className="ho-history-time mono">{new Date(h.captured_at).toLocaleString()}</span>
                    <span className="ho-history-by mono">{ownerLabel(h.finalized_by) || h.finalized_by}</span>
                  </button>
                ))}
              </div>
            )}
            {frozenError && (
              <div className="error-strip">
                <span>Snapshot failed to load: {frozenError}</span>
              </div>
            )}
          </div>
        </div>

        {/* Frozen-snapshot banner — also non-printing so the artifact stays clean. */}
        {frozen && frozenMeta && (
          <div className="ho-frozen-banner no-print">
            <span className="ho-frozen-tag">Viewing frozen snapshot</span>
            <span className="ho-frozen-meta mono">
              {frozenMeta.shift_label} · finalized {new Date(frozenMeta.captured_at).toLocaleString()} by{" "}
              {ownerLabel(frozenMeta.finalized_by) || frozenMeta.finalized_by}
            </span>
            <button className="btn" onClick={backToLive}>Back to live</button>
          </div>
        )}

        <ReportBody data={viewing} />
      </div>
    </div>
  );
}
