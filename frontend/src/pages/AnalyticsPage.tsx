import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import type { Analytics, EvalMiss, EvalSummary, ProtocolGapBreakdown } from "../types/api";
import { ownerLabel } from "../lib/format";

function errMsg(err: unknown): string {
  return err instanceof Error ? err.message : String(err);
}

function HBar({ value, max, color = "var(--signal-blue)" }: { value: number; max: number; color?: string }) {
  const pct = max === 0 ? 0 : Math.round((value / max) * 100);
  return (
    <div className="hbar">
      <div className="hbar-fill" style={{ width: `${pct}%`, background: color }} />
    </div>
  );
}

function Card({
  eyebrow,
  title,
  subtitle,
  children,
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="anal-card">
      <div className="anal-eyebrow">{eyebrow}</div>
      <h3 className="anal-title">{title}</h3>
      {subtitle && <div className="anal-sub">{subtitle}</div>}
      <div className="anal-body">{children}</div>
    </div>
  );
}

function ProtocolRow({ p, max }: { p: ProtocolGapBreakdown; max: number }) {
  return (
    <div className="anal-proto-row">
      <div className="anal-proto-head">
        <div className="anal-proto-name">{p.protocol_name}</div>
        <div className="anal-proto-stats">
          <span className="mono">{p.total_triggered} triggered</span>
          <span className="dim">·</span>
          <span className="mono red">{p.total_gaps} gaps</span>
        </div>
      </div>
      <HBar value={p.total_gaps} max={max} color="var(--signal-red)" />
      <div className="anal-proto-actions">
        {Object.entries(p.missing_by_action)
          .sort((a, b) => b[1] - a[1])
          .map(([label, count]) => (
            <div key={label} className="anal-proto-action">
              <span className="lbl">{label}</span>
              <span className="cnt mono">{count}</span>
            </div>
          ))}
      </div>
    </div>
  );
}

export function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evalData, setEvalData] = useState<EvalSummary | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [misses, setMisses] = useState<EvalMiss[] | null>(null);
  const [missesError, setMissesError] = useState<string | null>(null);
  const [missesLoading, setMissesLoading] = useState(false);
  const [showMisses, setShowMisses] = useState(false);

  useEffect(() => {
    const loadAll = () => {
      void (async () => {
        try {
          const d = await api.analytics();
          setData(d);
        } catch (err) {
          setError(errMsg(err));
        } finally {
          setLoading(false);
        }
      })();
      void api.evalSummary()
        .then((ev) => setEvalData(ev))
        .catch((err: unknown) => setEvalError(errMsg(err)));
      // Re-fetch named misses if the panel is open so they stay current.
      setMisses(null);
    };
    loadAll();
    // LIVE TICK mutates the floor; refresh cohort metrics + model card in place.
    const onRefresh = () => loadAll();
    window.addEventListener("radar:refresh", onRefresh);
    return () => window.removeEventListener("radar:refresh", onRefresh);
  }, []);

  const toggleMisses = async () => {
    if (showMisses) {
      setShowMisses(false);
      return;
    }
    setShowMisses(true);
    if (!misses && !missesLoading) {
      setMissesLoading(true);
      setMissesError(null); // clear any prior error so the loading state shows
      try {
        setMisses(await api.evalMisses());
      } catch (err) {
        setMissesError(errMsg(err));
      } finally {
        setMissesLoading(false);
      }
    }
  };

  if (loading) return <div className="empty-state">Loading analytics…</div>;
  if (!data) {
    return (
      <div className="anal-page">
        <div className="error-strip">
          <span>Analytics failed to load{error ? `: ${error}` : ""}</span>
        </div>
      </div>
    );
  }

  const urgencyTotal = Object.values(data.by_urgency).reduce((a, b) => a + b, 0);
  const maxGap = Math.max(1, ...data.by_protocol.map((p) => p.total_gaps));
  const maxAgeBucket = Math.max(1, ...Object.values(data.arrival_age_buckets));
  const maxOwner = Math.max(1, ...Object.values(data.actions_per_owner), ...Object.values(data.by_owner));

  return (
    <div className="anal-page">
      <div className="anal-topbar">
        <div className="anal-eyebrow">Hospital Operations · cohort metrics</div>
        <h1>Operational Analytics</h1>
        <div className="anal-sub">
          Same pipeline, aggregated across the {data.total_patients} patients on the floor right now.
          No PHI, all signals notional.
        </div>
      </div>

      <div className="anal-grid">
        <Card eyebrow="01 · Urgency mix" title="How the floor is loaded right now">
          <div className="anal-stack">
            {(["red", "amber", "green"] as const).map((u) => {
              const v = data.by_urgency[u] ?? 0;
              const pct = urgencyTotal === 0 ? 0 : Math.round((v / urgencyTotal) * 100);
              return (
                <div key={u} className="anal-stack-row">
                  <div className="lbl">
                    <span className={`urgency-pill ${u}`}><span className="dot" />{u.toUpperCase()}</span>
                  </div>
                  <HBar value={v} max={urgencyTotal} color={`var(--signal-${u})`} />
                  <div className="val mono">{v} <span className="dim">({pct}%)</span></div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card eyebrow="02 · Bottleneck mix" title="Which categories own the queue">
          <div className="anal-stack">
            {Object.entries(data.by_category)
              .sort((a, b) => b[1] - a[1])
              .map(([cat, n]) => (
                <div key={cat} className="anal-stack-row">
                  <div className="lbl mono small">{cat}</div>
                  <HBar value={n} max={data.total_patients} />
                  <div className="val mono">{n}</div>
                </div>
              ))}
          </div>
        </Card>

        <Card eyebrow="03 · Owner load" title="Who carries the work">
          <div className="anal-stack">
            {Object.entries(data.by_owner)
              .sort((a, b) => b[1] - a[1])
              .map(([owner, n]) => (
                <div key={owner} className="anal-stack-row">
                  <div className="lbl">{ownerLabel(owner)}</div>
                  <HBar value={n} max={maxOwner} />
                  <div className="val mono">{n}</div>
                </div>
              ))}
          </div>
        </Card>

        <Card eyebrow="04 · Time on floor" title="Length-of-stay distribution">
          <div className="anal-stack">
            {Object.entries(data.arrival_age_buckets).map(([b, n]) => (
              <div key={b} className="anal-stack-row">
                <div className="lbl mono">{b}</div>
                <HBar value={n} max={maxAgeBucket} />
                <div className="val mono">{n}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <Card
        eyebrow="05 · Protocol gaps"
        title="Where care pathways are silently failing"
        subtitle="Total documented action gaps across all triggered protocols. Highest-gap protocols routed first."
      >
        <div className="anal-protocols">
          {data.by_protocol.map((p) => (
            <ProtocolRow key={p.protocol_key} p={p} max={maxGap} />
          ))}
        </div>
      </Card>

      <div className="anal-grid">
        <Card eyebrow="06 · Silent failures" title="Floor-wide gap counts by protocol">
          <div className="anal-stack">
            {Object.entries(data.silent_failures_by_protocol)
              .sort((a, b) => b[1] - a[1])
              .map(([proto, n]) => (
                <div key={proto} className="anal-stack-row">
                  <div className="lbl small">{proto}</div>
                  <HBar value={n} max={Math.max(...Object.values(data.silent_failures_by_protocol), 1)} color="var(--signal-red)" />
                  <div className="val mono">{n}</div>
                </div>
              ))}
          </div>
        </Card>

        <Card eyebrow="07 · Action workflow" title="Active coordination load">
          <div className="anal-stack">
            {Object.entries(data.action_status).length === 0 ? (
              <div className="dim">No actions created yet. Create some from the queue to see flow data.</div>
            ) : (
              Object.entries(data.action_status).map(([s, n]) => (
                <div key={s} className="anal-stack-row">
                  <div className="lbl mono">{s.replace("_", " ")}</div>
                  <HBar value={n} max={Math.max(...Object.values(data.action_status), 1)} />
                  <div className="val mono">{n}</div>
                </div>
              ))
            )}
            {Object.entries(data.actions_per_owner).length > 0 && (
              <div className="anal-sub" style={{ marginTop: 12 }}>
                Open coordination tasks per role:
                {Object.entries(data.actions_per_owner).map(([o, n]) => (
                  <span key={o} className="tag" style={{ marginLeft: 6 }}>
                    {ownerLabel(o)} {n}
                  </span>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card
        eyebrow="08 · Model card"
        title="How well does the classifier actually perform"
        subtitle="Primary-bottleneck classification scored against hand-labeled ground truth for the full corpus."
      >
        {evalError ? (
          <div className="error-strip">
            <span>Eval summary failed to load: {evalError}</span>
          </div>
        ) : !evalData ? (
          <div className="dim mono small">Loading eval summary…</div>
        ) : (
          <>
            <div className="mc-stats">
              <div className="mc-stat">
                <span className="n">{(evalData.accuracy * 100).toFixed(1)}%</span>
                <span className="l">Corpus accuracy</span>
              </div>
              <div className="mc-stat">
                <span className="n">{(evalData.owner_routing.accuracy * 100).toFixed(1)}%</span>
                <span className="l">Owner routing</span>
              </div>
              <div className="mc-stat">
                <span className="n">{evalData.n}</span>
                <span className="l">Labeled notes</span>
              </div>
            </div>

            <div className="mc-table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Category</th>
                    <th style={{ textAlign: "right" }}>Precision</th>
                    <th style={{ textAlign: "right" }}>Recall</th>
                    <th style={{ textAlign: "right" }}>F1</th>
                    <th style={{ textAlign: "right" }}>Support</th>
                  </tr>
                </thead>
                <tbody>
                  {evalData.per_category.map((c) => (
                    <tr key={c.category}>
                      <td className="mono">{c.category}</td>
                      <td className="mono" style={{ textAlign: "right" }}>{c.precision.toFixed(2)}</td>
                      <td className="mono" style={{ textAlign: "right" }}>{c.recall.toFixed(2)}</td>
                      <td className="mono" style={{ textAlign: "right" }}>{c.f1.toFixed(2)}</td>
                      <td className="mono" style={{ textAlign: "right" }}>{c.support}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="mc-honesty">
              Measured against {evalData.n} held-out labels. The regression gate in CI
              fails any rule change that drops accuracy below the floor.{" "}
              100% = 44/44 note templates handled (4 generated notes per template) —
              template coverage, not paraphrase robustness. The owner-routing gap is a
              documented labeling inconsistency in 4 imaging templates: the corpus labels
              them physician, the engine routes imaging expediting to the floor nurse.
              Click <span className="mono">Show misses</span> to see all 16 by name.
            </div>

            <div className="mc-misses-row">
              <button className="btn" onClick={() => void toggleMisses()}>
                {showMisses ? "Hide misses" : "Show misses"}
              </button>
            </div>

            {showMisses && (
              missesError ? (
                <div className="error-strip" style={{ marginTop: "var(--s-3)" }}>
                  <span>Misses failed to load: {missesError}</span>
                </div>
              ) : missesLoading || !misses ? (
                <div className="dim mono small" style={{ marginTop: "var(--s-3)" }}>Loading misses…</div>
              ) : misses.length === 0 ? (
                <div className="dim mono small" style={{ marginTop: "var(--s-3)" }}>No misclassifications. Every label matched.</div>
              ) : (
                <div className="mc-table-wrap mc-misses">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Patient</th>
                        <th>Miss type</th>
                        <th>Truth</th>
                        <th>Predicted</th>
                        <th>Template</th>
                      </tr>
                    </thead>
                    <tbody>
                      {misses.map((m) => (
                        <tr key={`${m.miss_type}-${m.patient_id}`}>
                          <td className="mono"><Link to={`/p/${m.patient_id}`}>{m.patient_id}</Link></td>
                          <td className="mono dim">{m.miss_type}</td>
                          <td className="mono">{m.truth}</td>
                          <td className="mono" style={{ color: "var(--signal-red)" }}>{m.predicted}</td>
                          <td className="dim small">{m.template_name ?? "—"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )
            )}
          </>
        )}
      </Card>
    </div>
  );
}
