import { Link } from "react-router-dom";
import "../styles/landing.css";

const PROTOCOL_SHOWCASE: Array<{
  name: string;
  cite: string;
  triggers: string;
  actions: string[];
  owner: string;
  window: string;
}> = [
  {
    name: "Surviving Sepsis Hour-1 Bundle",
    cite: "Surviving Sepsis Campaign, 2018",
    triggers: "sepsis / septic / SIRS / lactate > 2 / hypotension",
    actions: ["Measure serum lactate", "Draw blood cultures pre-antibiotic", "Broad-spectrum antibiotics", "30 mL/kg crystalloid"],
    owner: "Physician",
    window: "1 hour",
  },
  {
    name: "NSTEMI / Unstable Angina",
    cite: "ACC/AHA Guidelines",
    triggers: "NSTEMI / chest pain + troponin / ST depression",
    actions: ["Aspirin 162–325 mg", "Anticoagulation", "Cardiology consult", "Serial troponin / ECG"],
    owner: "Physician",
    window: "2 hours",
  },
  {
    name: "Acute Ischemic Stroke",
    cite: "AHA/ASA Guidelines",
    triggers: "stroke / CVA / NIHSS / aphasia / hemiparesis",
    actions: ["Non-contrast head CT", "Stroke team activation", "tPA eligibility", "Blood pressure control"],
    owner: "Physician",
    window: "1 hour (window)",
  },
  {
    name: "Diabetic Ketoacidosis",
    cite: "ADA DKA Guidelines",
    triggers: "DKA / glucose > 300 / anion gap / β-OHB",
    actions: ["Insulin infusion", "IV fluid resuscitation", "K repletion", "Serial gap monitoring"],
    owner: "Physician",
    window: "2 hours",
  },
  {
    name: "Community-Acquired Pneumonia",
    cite: "IDSA/ATS Guidelines",
    triggers: "CAP / pneumonia / consolidation",
    actions: ["Empiric antibiotics ≤6h", "Blood cultures if severe", "Oxygenation assessed"],
    owner: "Physician",
    window: "6 hours",
  },
  {
    name: "Pulmonary Embolism",
    cite: "ESC/AHA PE Guidelines",
    triggers: "PE / suspected PE / D-dimer / right heart strain",
    actions: ["Therapeutic anticoagulation", "Confirmatory imaging", "Risk stratify (RV strain)", "Telemetry"],
    owner: "Physician",
    window: "2 hours",
  },
  {
    name: "Upper GI Bleed",
    cite: "ACG GIB Guidelines",
    triggers: "GIB / melena / hematemesis / hgb drop",
    actions: ["Two large-bore IV", "Type and screen", "IV PPI", "GI / endoscopy"],
    owner: "Physician",
    window: "2 hours",
  },
  {
    name: "Acute Kidney Injury Workup",
    cite: "KDIGO AKI Guidelines",
    triggers: "creatinine rise / oliguria / AKI",
    actions: ["Medication review", "Volume status", "Urine studies (FENa)", "Renal US"],
    owner: "Physician",
    window: "12 hours",
  },
  {
    name: "Alcohol Withdrawal (CIWA)",
    cite: "ASAM Guidelines",
    triggers: "alcohol withdrawal / CIWA / history of DTs",
    actions: ["CIWA scoring q1–2h", "Benzodiazepine protocol", "Thiamine / banana bag", "Seizure precautions"],
    owner: "Physician",
    window: "2 hours",
  },
  {
    name: "Neutropenic Fever",
    cite: "IDSA Febrile Neutropenia",
    triggers: "fever + ANC < 500 / febrile neutropenia",
    actions: ["Empiric antibiotics ≤60 min", "Blood cultures × 2", "Neutropenic precautions", "Oncology notified"],
    owner: "Physician",
    window: "1 hour",
  },
  {
    name: "Severe Hyperkalemia",
    cite: "ESC/AHA Consensus",
    triggers: "K ≥ 6.0 / peaked T-waves",
    actions: ["ECG", "Calcium gluconate", "Insulin + D50", "Removal: diuretic / dialysis / binders"],
    owner: "Physician",
    window: "1 hour",
  },
  {
    name: "COPD Exacerbation",
    cite: "GOLD Strategy",
    triggers: "COPD exacerbation / AECOPD",
    actions: ["Bronchodilator", "Systemic steroids", "Antibiotics (if purulent)", "Controlled O2 88–92%"],
    owner: "Physician",
    window: "4 hours",
  },
];

const CATEGORIES: Array<{ name: string; example: string; owner: string }> = [
  {
    name: "Missing standard-of-care step",
    example: "Sepsis bundle triggered but antibiotics aren't documented within hour-1 window.",
    owner: "Physician",
  },
  {
    name: "Medication safety risk",
    example: "Patient on apixaban + ibuprofen + aspirin with hgb drop and melena.",
    owner: "Pharmacist",
  },
  {
    name: "Awaiting specialist consult",
    example: "Hip fracture, ortho consult requested 14h ago, no callback in chart.",
    owner: "Physician",
  },
  {
    name: "Awaiting imaging",
    example: "RLQ pain, CT abd ordered 5h ago, still in queue per radiology.",
    owner: "Nurse",
  },
  {
    name: "Discharge / placement delay",
    example: "Medically ready but SNF declined; insurance auth pending for 3 days.",
    owner: "Case manager",
  },
  {
    name: "High readmission risk",
    example: "Third DKA in 8 months, no PCP follow-up, intermittent housing.",
    owner: "Case manager",
  },
  {
    name: "Clear",
    example: "No active operational, safety, or protocol gaps detected.",
    owner: "—",
  },
];

const FAQ: Array<{ q: string; a: string }> = [
  {
    q: "Is this a clinical decision aid?",
    a: "No. The console does not provide diagnoses, treatment recommendations, or any clinical judgment. Every signal surfaced — a missing documented step, an awaited consult, a placement hold — is an operational coordination signal. The clinician decides what to do; the tool just makes sure the decision doesn't fall off the board.",
  },
  {
    q: "Where does the LLM live in this pipeline?",
    a: "Optionally, in the entity extractor on the Foundry build. Locally it's a regex extractor for inspectability. No LLM is in the path that produces a recommendation. Protocol gaps and bottleneck classification are deterministic rules with named citations. This is the right line to hold for the Use Case Restriction on clinical decision aids.",
  },
  {
    q: "Why deterministic rules instead of a single classifier?",
    a: "Triage on a floor is a cascade: red-flag the dangerous miss, then the safety risk, then the workflow blockers, then the dispo holds. Rules are easier to audit, easier for a charge nurse to push back on, and trivially explainable in a 30-second handoff. A black-box classifier can't tell you which sentence in the note fired it.",
  },
  {
    q: "How real is the data?",
    a: "Entirely notional. Notes are synthesized from 27 templates that encode realistic bottleneck patterns, then varied for age, sex, and arrival time. 176 patients in the demo, spread across 6 wings and 180 beds. No PHI, no real chart text. The same pipeline runs unchanged on real notes in a Foundry deployment with the appropriate ontology.",
  },
  {
    q: "Why 12 care pathways?",
    a: "They cover the high-acuity, high-volume, time-sensitive bundles that hospital throughput committees actually track. Adding a thirteenth is a config change, not a code change — protocols are data, with triggers, expected actions, owners, time windows and citations.",
  },
  {
    q: "What's the audit trail story?",
    a: "Every action carries an immutable event log: created, status changes, owner reassignments. Every gap links to the protocol it was matched against, the exact sentence in the note that triggered it, and the citation backing the standard. The whole thing is built so a quality officer can answer 'why did this fire' in one click.",
  },
];

export function LandingPage() {
  return (
    <div className="landing">
      <div className="landing-top">
        <div className="container landing-top-inner">
          <div className="landing-mark">
            <span className="glyph" />
            <span>Bottleneck&nbsp;Radar</span>
          </div>
          <div className="landing-meta">
            <span>v0.2</span>
            <span className="dot">·</span>
            <span>Notional data</span>
            <span className="dot">·</span>
            <span>Floors 3–5 · 180 beds</span>
          </div>
        </div>
      </div>

      <section className="hero">
        <div className="container hero-grid">
          <div>
            <div className="hero-eyebrow">Hospital Operations · Throughput Intelligence</div>
            <h1 className="hero-title">
              Every patient on the floor has a reason they aren't moving.{" "}
              <span className="em">Make that reason legible to operations.</span>
            </h1>
            <p className="hero-lede">
              Bottleneck Radar is an operational coordination tool for hospital
              throughput, not a clinical decision aid. It reads the same notes a
              charge nurse already reads and surfaces, in one screen, where each
              patient is in the workflow, which documented step is missing, and
              which role on the floor owns the next coordination action. All
              clinical judgment stays with the care team.
            </p>

            <div className="cta-row">
              <Link to="/dashboard" className="cta-primary">
                <span>Enter the operations console</span>
                <span className="arrow">→</span>
              </Link>
              <Link to="/floor" className="cta-secondary">View the floor map</Link>
              <a href="#how" className="cta-secondary">How it works</a>
            </div>
          </div>

          <aside className="facts">
            <h4>Live snapshot · all wings</h4>
            <dl>
              <dt>Patients tracked</dt><dd>176</dd>
              <dt>Beds (6 wings)</dt><dd>180</dd>
              <dt>Critical right now</dt><dd>64</dd>
              <dt>Silent protocol gaps</dt><dd>196</dd>
              <dt>Care pathways modeled</dt><dd>12</dd>
              <dt>ICD-10 reference set</dt><dd>39 codes</dd>
              <dt>Bottleneck categories</dt><dd>7</dd>
              <dt>Note templates</dt><dd>27</dd>
            </dl>
            <p className="footnote">
              All cases in the console are notional and generated for this
              demonstration. No real patient data is used. The same pipeline
              runs unchanged on real notes when deployed against a Foundry
              ontology with appropriate review and safety controls.
            </p>
          </aside>
        </div>
      </section>

      <section className="section-pad" id="how">
        <div className="container">
          <div className="section-eyebrow">Pipeline</div>
          <h2 className="section-title">From a free-text note to an action with an owner.</h2>
          <p className="section-blurb">
            The console doesn't summarize charts. It runs a deterministic
            pipeline that produces the same answer every time, with each step
            inspectable on the patient detail page.
          </p>

          <div className="pipeline">
            <div className="pipeline-step">
              <div className="num">01 · Read</div>
              <h3>Ingest the H&amp;P</h3>
              <p>
                The note is parsed into structured entities — vitals, labs,
                medications, dispositional signals (placement need, isolation,
                consult requested), prior diagnoses.
              </p>
              <div className="tech">spaCy-style entity extractor · 70+ patterns</div>
            </div>
            <div className="pipeline-step">
              <div className="num">02 · Locate</div>
              <h3>Map to ICD-10</h3>
              <p>
                A TF-IDF retriever ranks the top differential candidates against
                a curated reference of high-acuity codes — sepsis, AKI, NSTEMI,
                CVA, DKA, CAP and others — surfaced with a confidence score.
              </p>
              <div className="tech">scikit-learn · 39-code reference set</div>
            </div>
            <div className="pipeline-step">
              <div className="num">03 · Compare</div>
              <h3>Match against protocol</h3>
              <p>
                Each candidate condition triggers a care pathway: Surviving
                Sepsis, ACS, the tPA stroke window, IDSA CAP, ADA DKA, plus
                seven more. Documented steps go green; missing steps go red.
              </p>
              <div className="tech">12 protocols · timed windows enforced</div>
            </div>
            <div className="pipeline-step">
              <div className="num">04 · Route</div>
              <h3>Classify the bottleneck</h3>
              <p>
                A rule engine ranks open issues across seven operational
                categories and surfaces the coordination step that needs
                someone's attention — and which role on the floor owns it.
                The clinician decides what to do.
              </p>
              <div className="tech">Deterministic cascade · audit trail attached</div>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad">
        <div className="container two-col">
          <div>
            <div className="section-eyebrow">Why this exists</div>
            <h2 className="section-title">Throughput is a triage problem, not a dashboard problem.</h2>
            <p>
              Every hospital already has census boards, EMR worklists and
              capacity huddles. They tell you a patient has been on the floor
              for 47 hours. They don't tell you that the only thing standing
              between that patient and discharge is a SNF bed that nobody has
              called for, or that a sepsis bundle was started but antibiotics
              were never charted.
            </p>
            <p>
              Bottleneck Radar is built to answer the question a charge nurse
              actually asks at the start of a shift:{" "}
              <em>which seven of these one-hundred-and-seventy-six patients
              should I touch first, and what specifically am I doing about
              each one?</em>
            </p>
          </div>

          <div>
            <div className="section-eyebrow">Bottleneck taxonomy</div>
            <h3>Seven categories, mutually exclusive, owner attached.</h3>
            <ul className="numbered">
              {CATEGORIES.map((c) => (
                <li key={c.name}>
                  <span>
                    <strong style={{ color: "var(--ink)" }}>{c.name}</strong> · {c.owner}
                    <div style={{ fontSize: 12.5, color: "var(--ink-3)", marginTop: 4 }}>{c.example}</div>
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="section-pad">
        <div className="container">
          <div className="section-eyebrow">Worked example · P-1001</div>
          <h2 className="section-title">A 68-year-old with a sepsis-bundle gap, in three reads.</h2>
          <p className="section-blurb">
            This is one of the one-hundred-and-seventy-six notes in the corpus.
            The same pipeline runs end-to-end on every patient in the console.
          </p>

          <div className="sample">
            <div className="sample-head">
              <span>Note · P-1001 · 68 F · arrived 2.1d ago</span>
              <span className="pill">Critical</span>
            </div>
            <div className="sample-body">
{`HPI: 72yo presenting from SNF with fever to 39.4C, BP 88/52, HR 122,
RR 24, SpO2 91% on room air. Family reports two days of decreased PO
intake and confusion. PMH: HTN, DM2, recurrent UTI.

Labs: WBC 18.2, lactate 3.1, creatinine 1.9 (baseline 1.0), UA cloudy
with many bacteria and 50+ WBC/hpf. Blood cultures drawn.

Assessment: severe sepsis, urinary source. Meets `}<span className="ev red">SIRS</span>{` criteria
with end-organ dysfunction.
Plan: IV fluids 30 mL/kg bolus initiated. Will trend lactate. Admit
to medicine.`}
            </div>
            <div className="verdict">
              <span className="k">ICD-10 candidate</span><span className="v">R65.20 · severe sepsis without septic shock (0.42)</span>
              <span className="k">Protocol</span><span className="v">Surviving Sepsis Hour-1 Bundle · 1 documented step missing</span>
              <span className="k">Missing step</span><span className="v">Administer broad-spectrum antibiotics</span>
              <span className="k">Operational signal</span><span className="v bad">Documentation gap, standard-of-care step</span>
              <span className="k">Owner role</span><span className="v">Physician on the floor</span>
              <span className="k">Coordination</span><span className="v">Surface gap to owning role; clinical decision stays with the care team</span>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad">
        <div className="container">
          <div className="section-eyebrow">Protocol library</div>
          <h2 className="section-title">Twelve published care pathways, encoded as data.</h2>
          <p className="section-blurb">
            Each protocol is structured: triggers, expected actions, owner,
            urgency-if-incomplete, time window, and citation. Adding the
            thirteenth is a config change. The list isn't exhaustive — it's
            the high-acuity bundles that hospital throughput committees
            actually track.
          </p>

          <div className="protocol-grid">
            {PROTOCOL_SHOWCASE.map((p) => (
              <div key={p.name} className="protocol-card">
                <div className="pc-head">
                  <div className="pc-name">{p.name}</div>
                  <div className="pc-window">{p.window}</div>
                </div>
                <div className="pc-cite">{p.cite}</div>
                <div className="pc-triggers"><span>Triggers when</span>{p.triggers}</div>
                <ul className="pc-actions">
                  {p.actions.map((a) => <li key={a}>{a}</li>)}
                </ul>
                <div className="pc-owner">Owner: {p.owner}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="section-pad" style={{ background: "var(--paper-2)" }}>
        <div className="container">
          <div className="section-eyebrow">What you see in the console</div>
          <h2 className="section-title">Five views, one operational pipeline behind them.</h2>
          <p className="section-blurb">
            The same data backs every screen. The console is intentionally
            calm: monochrome surfaces, signal color reserved for urgency,
            monospace digits so numbers line up. It's meant to look more like
            a Bloomberg terminal than a consumer app, because the users are
            checking it every fifteen minutes during a shift.
          </p>

          <div className="view-grid">
            <div className="view-card">
              <div className="vc-mock vc-queue">
                <div className="vcm-strip">
                  <span className="vcm-pill red">21</span>
                  <span className="vcm-pill amber">29</span>
                  <span className="vcm-pill green">26</span>
                  <span className="vcm-spacer" />
                  <span className="vcm-search">▢ search…</span>
                </div>
                <div className="vcm-rows">
                  <div className="vcm-row r">P-1001 · 3E-04 · 68F · missing SoC · Physician</div>
                  <div className="vcm-row r">P-1014 · 3E-11 · 56M · missing SoC · Physician</div>
                  <div className="vcm-row a">P-1028 · 3W-02 · 71F · await consult · Physician</div>
                  <div className="vcm-row a">P-1039 · 4E-09 · 80M · med risk · Pharmacist</div>
                  <div className="vcm-row g">P-1056 · 5E-12 · 38F · clear · —</div>
                </div>
              </div>
              <h4>Queue</h4>
              <p>Every patient on the floor, ranked by urgency. Filter by owner, category, or free text. Bulk-route a slice with one action.</p>
            </div>

            <div className="view-card">
              <div className="vc-mock vc-floor">
                <div className="vcm-floorgrid">
                  {Array.from({ length: 24 }).map((_, i) => (
                    <div key={i} className={`vcm-bed ${["r", "a", "g", "", "", ""][i % 6]}`} />
                  ))}
                </div>
              </div>
              <h4>Floor map</h4>
              <p>Spatial view of all 180 beds, colored by urgency. Charge RN sees where the critical patients clustering at the end of the wing are.</p>
            </div>

            <div className="view-card">
              <div className="vc-mock vc-analytics">
                <div className="vcm-bars">
                  <div className="vcm-bar" style={{ height: "70%", background: "var(--accent)" }} />
                  <div className="vcm-bar" style={{ height: "52%" }} />
                  <div className="vcm-bar" style={{ height: "44%" }} />
                  <div className="vcm-bar" style={{ height: "30%" }} />
                  <div className="vcm-bar" style={{ height: "22%" }} />
                  <div className="vcm-bar" style={{ height: "18%" }} />
                </div>
              </div>
              <h4>Analytics</h4>
              <p>Cohort metrics — gap distribution by protocol, owner load, length-of-stay buckets. Quality committee starting point.</p>
            </div>

            <div className="view-card">
              <div className="vc-mock vc-handoff">
                <div className="vcm-paper">
                  <div className="vcm-paper-h">01 · Critical</div>
                  <div className="vcm-paper-l">P-1001 · sepsis bundle gap</div>
                  <div className="vcm-paper-l">P-1014 · NSTEMI · cards consult</div>
                  <div className="vcm-paper-h">02 · Gaps</div>
                  <div className="vcm-paper-l">P-1028 · stroke · tPA eval</div>
                </div>
              </div>
              <h4>Shift handoff</h4>
              <p>Printable artifact for shift change. The list of what matters tonight: critical patients, open gaps, dispo holds, work-by-owner.</p>
            </div>
          </div>
        </div>
      </section>

      <section className="section-pad">
        <div className="container two-col">
          <div>
            <div className="section-eyebrow">Architecture</div>
            <h3>FastAPI on the backend, dense React on the front.</h3>
            <p>
              The backend is a typed FastAPI service over SQLite — a stand-in
              for a Foundry ontology in this prototype. Every entity, every
              ICD-10 candidate, every protocol gap and every action is a row
              you can query directly. The frontend treats the API as the
              source of truth and adds nothing of its own.
            </p>
            <p>
              The Foundry export folder ships everything to lift the same
              pipeline into AIP: four CSVs for the raw layer, an ontology
              spec, a self-contained Python transform for the protocol-gap
              pipeline, the function spec for{" "}
              <em>classify_bottleneck</em>, and a Workshop storyboard.
            </p>
          </div>
          <div>
            <div className="section-eyebrow">What it isn't</div>
            <h3>Not a clinical decision aid. Not a chatbot. Not a chart-writer.</h3>
            <p>
              Bottleneck Radar does not provide clinical judgment, medical
              advice, diagnosis or therapy, and is not intended as a medical
              device. It does not generate clinical text. It surfaces
              operational signals — a documentation gap against a published
              care pathway, a missing consult ack, a placement delay — and
              routes them to the role on the floor that handles that kind
              of coordination work.
            </p>
            <p>
              Every signal in the console links back to the specific span of
              the note that triggered it and the protocol it was compared
              against. That is the audit trail. Every clinical decision
              still belongs to the care team.
            </p>
          </div>
        </div>
      </section>

      <section className="section-pad">
        <div className="container">
          <div className="section-eyebrow">Honest answers</div>
          <h2 className="section-title">Questions you'd ask if you actually had to deploy this.</h2>
          <div className="faq">
            {FAQ.map((f, i) => (
              <details key={i} className="faq-item">
                <summary>{f.q}</summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      <section className="section-pad" style={{ borderBottom: "none" }}>
        <div className="container" style={{ textAlign: "center", maxWidth: 720 }}>
          <h2 className="section-title" style={{ fontSize: 36 }}>
            The console is open. One-seventy-six patients are on the floor.
          </h2>
          <p className="section-blurb" style={{ margin: "0 auto 32px" }}>
            One of them has a documented care-pathway step missing from the
            chart. See if you can find them in under thirty seconds.
          </p>
          <Link to="/dashboard" className="cta-primary">
            <span>Enter the operations console</span>
            <span className="arrow">→</span>
          </Link>
          <p style={{ marginTop: 36, fontSize: 12, color: "var(--ink-3)", fontFamily: "var(--font-mono)", lineHeight: 1.6 }}>
            For demonstration purposes only · operational coordination tool ·
            not a clinical decision aid · not a medical device · all clinical
            judgment remains with licensed care team members
          </p>
        </div>
      </section>

      <footer className="landing-foot">
        <div className="container row">
          <span>Bottleneck Radar · built for the Palantir AIP build challenge</span>
          <span>Notional data only · no PHI</span>
        </div>
      </footer>
    </div>
  );
}
