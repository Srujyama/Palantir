import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { HandoffReport, HandoffSection } from "../types/api";
import { ownerLabel } from "../lib/format";

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

export function HandoffPage() {
  const [data, setData] = useState<HandoffReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void (async () => {
      try {
        const d = await api.handoff();
        setData(d);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading || !data) return <div className="empty-state">Building handoff report…</div>;

  return (
    <div className="ho-page">
      <div className="ho-paper">
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
          <div className="ho-actions no-print">
            <button className="btn primary" onClick={() => window.print()}>Print this report</button>
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
      </div>
    </div>
  );
}
