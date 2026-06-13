import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { api } from "../lib/api";
import type {
  Extraction,
  Finding,
  ICDCandidate,
  ProtocolMatch,
  SandboxResult,
  SandboxSample,
} from "../types/api";
import { categoryShort } from "../lib/format";
import { BottleneckCard } from "../components/BottleneckCard";
import { NoteWithEvidence } from "../components/NoteWithEvidence";
import "../styles/sandbox.css";

const MIN_CHARS = 20;
const RUN_STAGES = ["extract", "classify", "icd", "decide"] as const;

const EXTRACT_CATS: { key: keyof Extraction; label: string }[] = [
  { key: "vitals", label: "Vitals" },
  { key: "labs", label: "Labs" },
  { key: "meds", label: "Meds" },
  { key: "symptoms", label: "Symptoms" },
  { key: "consults", label: "Consults" },
  { key: "imaging", label: "Imaging" },
  { key: "dispo", label: "Dispo" },
  { key: "risk_factors", label: "Risk" },
];

// ── Stage shell ──────────────────────────────────────────────────────────

function Stage({ n, title, note, children }: { n: string; title: string; note?: string; children: ReactNode }) {
  return (
    <div className="section sb-stage">
      <div className="head">
        <span className="sb-stage-num">[{n}]</span>
        <span className="label bright">{title}</span>
        {note && <span className="sb-stage-note dim small">{note}</span>}
      </div>
      <div className="body">{children}</div>
    </div>
  );
}

// ── [1] Entity extraction ────────────────────────────────────────────────

function FindingChip({ f, upper, meta }: { f: Finding; upper?: boolean; meta?: "class" | "status" }) {
  const negated = Boolean(f.metadata?.negated);
  const suffix = meta ? f.metadata?.[meta] : undefined;
  const base = f.label.replace(/_/g, " ");
  return (
    <span className={`tag sb-chip${negated ? " sb-neg" : ""}`} title={f.evidence.text}>
      <span className="sb-chip-label">{upper ? base.toUpperCase() : base}</span>
      {f.value ? <span className="sb-chip-val mono">{f.value}</span> : null}
      {suffix ? <span className="sb-chip-cls">{suffix}</span> : null}
      {negated ? <span className="sb-neg-tag">NEG</span> : null}
    </span>
  );
}

function ChipGroup({
  label, findings, upper, meta,
}: { label: string; findings: Finding[]; upper?: boolean; meta?: "class" | "status" }) {
  if (!findings.length) return null;
  return (
    <div className="sb-chip-group">
      <div className="sb-micro">{label}</div>
      <div className="entities">
        {findings.map((f, i) => (
          <FindingChip key={`${f.label}-${i}`} f={f} upper={upper} meta={meta} />
        ))}
      </div>
    </div>
  );
}

function ExtractStage({ ext }: { ext: Extraction }) {
  return (
    <div>
      <div className="sb-counts">
        {EXTRACT_CATS.map((c) => {
          const n = (ext[c.key] ?? []).length;
          return (
            <div key={c.key} className={`sb-count${n === 0 ? " zero" : ""}`}>
              <span className="sb-count-n mono">{n}</span>
              <span className="sb-count-l">{c.label}</span>
            </div>
          );
        })}
      </div>
      <ChipGroup label="Medications" findings={ext.meds} meta="class" />
      <ChipGroup label="Labs" findings={ext.labs} />
      <ChipGroup label="Symptoms" findings={ext.symptoms} />
      <ChipGroup label="Consults" findings={ext.consults} meta="status" />
      <ChipGroup label="Imaging" findings={ext.imaging} upper meta="status" />
      <ChipGroup label="Dispo signals" findings={ext.dispo} />
      <ChipGroup label="Risk markers" findings={ext.risk_factors} />
    </div>
  );
}

// ── [2] ICD-10 retrieval ─────────────────────────────────────────────────

function IcdStage({ candidates }: { candidates: ICDCandidate[] }) {
  if (!candidates.length) {
    return <div className="dim mono small">No ICD-10 candidates above threshold.</div>;
  }
  const max = Math.max(...candidates.map((c) => c.score), 0.0001);
  return (
    <div className="sb-icd">
      {candidates.slice(0, 5).map((c) => (
        <div key={c.code} className="sb-icd-row">
          <span className="tag code">{c.code}</span>
          <span className="sb-icd-desc" title={c.description}>{c.description}</span>
          <div className="hbar">
            <div className="hbar-fill" style={{ width: `${Math.max(4, (c.score / max) * 100)}%` }} />
          </div>
          <span className="mono sb-icd-score">{c.score.toFixed(2)}</span>
        </div>
      ))}
    </div>
  );
}

// ── [3] Protocol evaluation ──────────────────────────────────────────────

function ProtocolStage({ matches }: { matches: ProtocolMatch[] }) {
  const triggered = matches.filter((m) => m.triggered);
  if (!triggered.length) {
    return <div className="dim mono small">No protocols triggered by this note.</div>;
  }
  return (
    <table className="protocol-table">
      <thead>
        <tr>
          <th style={{ width: "36%" }}>Protocol</th>
          <th style={{ width: 130 }}>Steps</th>
          <th>Missing steps</th>
        </tr>
      </thead>
      <tbody>
        {triggered.map((m) => (
          <tr key={m.protocol_key}>
            <td>
              <div style={{ color: "var(--fg-0)" }}>{m.protocol_name}</div>
              <div className="sb-cite">{m.citation} · {m.time_window_hours}h window</div>
            </td>
            <td className="mono small">
              <span className="ok">{m.documented.length} documented</span>
              <br />
              <span className={m.missing.length ? "miss" : "dim"}>{m.missing.length} missing</span>
            </td>
            <td>
              {m.missing.length === 0 ? (
                <span className="ok mono small">COMPLETE</span>
              ) : (
                <ul className="sb-miss-list">
                  {m.missing.map((s, i) => <li key={i} className="miss">{s}</li>)}
                </ul>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────

export function SandboxPage() {
  const [samples, setSamples] = useState<SandboxSample[] | null>(null);
  const [samplesError, setSamplesError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [running, setRunning] = useState(false);
  const [runStage, setRunStage] = useState(0);
  const [result, setResult] = useState<{ res: SandboxResult; note: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    let alive = true;
    api.sandboxSamples()
      .then((s) => { if (alive) setSamples(s); })
      .catch((e: unknown) => {
        if (alive) {
          setSamples([]);
          setSamplesError(e instanceof Error ? e.message : String(e));
        }
      });
    return () => {
      alive = false;
      if (timerRef.current !== null) window.clearInterval(timerRef.current);
    };
  }, []);

  const canRun = note.trim().length >= MIN_CHARS && !running;

  const run = async () => {
    if (!canRun) return;
    const submitted = note;
    setRunning(true);
    setError(null);
    setRunStage(0);
    timerRef.current = window.setInterval(() => {
      setRunStage((s) => Math.min(s + 1, RUN_STAGES.length - 1));
    }, 140);
    // Keep the staged strip visible for a beat even though the engine is ~30ms.
    const minWait = new Promise((resolve) => setTimeout(resolve, 620));
    try {
      const [r] = await Promise.all([api.sandboxTriage({ note_text: submitted }), minWait]);
      setResult({ res: r, note: submitted });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (timerRef.current !== null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setRunning(false);
    }
  };

  const r = result?.res ?? null;
  const evSpans = r
    ? [
        ...r.triage.primary.evidence.map((s) => ({
          span: s,
          level: r.triage.primary.urgency === "red" ? ("red" as const) : ("amber" as const),
        })),
        ...r.triage.secondary.flatMap((b) =>
          b.evidence.map((s) => ({
            span: s,
            level: b.urgency === "red" ? ("red" as const) : ("amber" as const),
          })),
        ),
        ...r.triage.silent_failures.map((sf) => ({
          span: sf.trigger_evidence,
          level: sf.urgency === "red" ? ("red" as const) : ("amber" as const),
        })),
      ]
    : [];

  return (
    <div className="sb-page">
      <div className="sb-topbar">
        <div className="t-eyebrow">Under the hood</div>
        <h1>Triage sandbox</h1>
        <div className="t-sub">
          Paste any clinical note and watch the deterministic pipeline run stage by stage —
          extraction, ICD-10 retrieval, protocol evaluation, bottleneck decision. Every signal
          traces to an evidence span and a cited protocol. Nothing is persisted.
        </div>
      </div>

      <div className="sb-grid">
        {/* ── Left: note editor ─────────────────────────────────────── */}
        <div className="sb-left">
          <div className="section sb-editor">
            <div className="head">
              <span className="label bright">Note editor</span>
              <span className="sb-head-hint">⌘⏎ / Ctrl⏎ runs</span>
            </div>
            <div className="body">
              <textarea
                className="sb-textarea"
                rows={14}
                spellCheck={false}
                placeholder="Paste any clinical note here, or pick a sample below…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                    e.preventDefault();
                    void run();
                  }
                }}
              />
              <div className="sb-editor-foot">
                <span className="sb-charcount mono">
                  {note.length} chars
                  {note.trim().length < MIN_CHARS && <span className="dim"> · min {MIN_CHARS}</span>}
                </span>
                <button className="btn primary" disabled={!canRun} onClick={() => void run()}>
                  {running ? "Running…" : "Run pipeline"}
                </button>
              </div>
              {running && (
                <div className="sb-progress">
                  {RUN_STAGES.map((s, i) => (
                    <span
                      key={s}
                      className={`sb-progress-cell${i < runStage ? " done" : ""}${i === runStage ? " active" : ""}`}
                    >
                      {s}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="section">
            <div className="head"><span className="label">Sample notes</span></div>
            <div className="body">
              {samples === null && <div className="dim mono small">Loading samples…</div>}
              {samplesError && (
                <div className="sb-error small">SAMPLES FAILED TO LOAD · {samplesError}</div>
              )}
              {samples !== null && samples.length === 0 && !samplesError && (
                <div className="dim mono small">No samples available.</div>
              )}
              {samples !== null && samples.length > 0 && (
                <div className="sb-samples">
                  {samples.map((s) => (
                    <button
                      key={s.key}
                      className="sb-sample"
                      title={s.label}
                      onClick={() => { setNote(s.note_text); setError(null); }}
                    >
                      <span className="sb-sample-label">{s.label}</span>
                      <span className="tag subtle">{categoryShort(s.expected_category)}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* ── Right: pipeline trace ─────────────────────────────────── */}
        <div className="sb-right">
          {error && <div className="sb-error">PIPELINE ERROR · {error}</div>}
          {error && result && (
            <div className="sb-stale mono">Showing the last successful run below.</div>
          )}

          {!result && !error && (
            <div className="empty-state sb-empty">
              Deterministic pipeline. No LLM in the recommendation path.
              <br />
              Paste a note, see every step.
            </div>
          )}

          {result && r && (
            <div className="sb-stages">
              <Stage n="1" title="Entity extraction">
                <ExtractStage ext={r.extraction} />
              </Stage>

              <Stage n="2" title="ICD-10 retrieval" note="display-only context — never an input to the decision">
                <IcdStage candidates={r.icd_candidates} />
              </Stage>

              <Stage n="3" title="Protocol evaluation">
                <ProtocolStage matches={r.triage.protocol_matches} />
              </Stage>

              <Stage n="4" title="Bottleneck decision">
                <BottleneckCard b={r.triage.primary} isPrimary />
                {r.triage.secondary.map((b, i) => <BottleneckCard key={i} b={b} />)}
                <div className="sb-micro sb-note-label">Note · evidence highlighted</div>
                <NoteWithEvidence text={result.note} spans={evSpans} />
              </Stage>

              <div className="sb-timings mono">
                <span>
                  extract {r.stage_timings_ms.extract.toFixed(1)}ms
                  {" · "}classify {r.stage_timings_ms.classify.toFixed(1)}ms
                  {" · "}icd {r.stage_timings_ms.icd.toFixed(1)}ms
                  {" · "}total {r.stage_timings_ms.total.toFixed(1)}ms
                </span>
                <span className="sb-timings-engine">
                  engine v{r.engine.version} · {r.engine.protocols_evaluated} protocols
                  {" · "}{r.engine.categories} categories
                </span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
