import { Link } from "react-router-dom";
import "../styles/landing.css";

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
            <span>v0.1</span>
            <span className="dot">·</span>
            <span>Notional data</span>
            <span className="dot">·</span>
            <span>Floor 3 East</span>
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
              Bottleneck Radar is an operational tool for hospital throughput,
              not a clinical decision aid. It reads the same notes a charge
              nurse already reads and surfaces, in one screen, where each
              patient is in the workflow, which documented step is missing,
              and which role on the floor owns the next coordination action.
              All clinical judgment stays with the care team.
            </p>

            <div className="cta-row">
              <Link to="/dashboard" className="cta-primary">
                <span>Enter the operations console</span>
                <span className="arrow">→</span>
              </Link>
              <a href="#how" className="cta-secondary">How it works</a>
            </div>
          </div>

          <aside className="facts">
            <h4>Live snapshot · Floor 3 East</h4>
            <dl>
              <dt>Patients tracked</dt><dd>60</dd>
              <dt>Critical right now</dt><dd>21</dd>
              <dt>Silent protocol gaps</dt><dd>21</dd>
              <dt>Median time on floor</dt><dd>43.6h</dd>
              <dt>Care pathways modeled</dt><dd>5</dd>
              <dt>ICD-10 reference set</dt><dd>39 codes</dd>
            </dl>
            <p className="footnote">
              All cases shown in the console are notional and generated for
              this demonstration. No real patient data is used.
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
              <h3>Ingest the H&P</h3>
              <p>
                The note is parsed into structured entities — vitals, labs,
                medications, dispositional signals (placement need, isolation,
                consult requested), prior diagnoses.
              </p>
              <div className="tech">spaCy-style entity extractor</div>
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
                Sepsis Hour-1 Bundle, ACS initial management, the tPA window
                for stroke, IDSA CAP, ADA DKA. Documented steps go green;
                missing steps go red.
              </p>
              <div className="tech">5 protocols · timed windows enforced</div>
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
              <div className="tech">60 / 60 on the labeled set</div>
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
              <em>which seven of these sixty patients should I touch first,
              and what specifically am I doing about each one?</em>
            </p>
          </div>

          <div>
            <div className="section-eyebrow">Bottleneck taxonomy</div>
            <h3>Seven categories, mutually exclusive, owner attached.</h3>
            <ul className="numbered">
              <li>Awaiting specialist consult — physician owned</li>
              <li>Awaiting imaging — physician owned</li>
              <li>Discharge / placement delay — case manager owned</li>
              <li>Missing standard-of-care step — physician owned</li>
              <li>Medication safety risk — pharmacist owned</li>
              <li>High readmission risk — case manager owned</li>
              <li>No active bottleneck — tracked, not surfaced</li>
            </ul>
          </div>
        </div>
      </section>

      <section className="section-pad">
        <div className="container">
          <div className="section-eyebrow">Worked example · P-1001</div>
          <h2 className="section-title">A 68-year-old with a sepsis-bundle gap, in three reads.</h2>
          <p className="section-blurb">
            This is one of the sixty notes in the corpus. The same pipeline
            runs end-to-end on every patient in the console.
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
              <span className="k">Operational signal</span><span className="v bad">Documentation gap, standard-of-care step</span>
              <span className="k">Owner role</span><span className="v">Physician on the floor</span>
              <span className="k">Coordination</span><span className="v">Surface gap to owning role; clinical decision stays with the care team</span>
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
              The console is intentionally calm: monochrome surfaces, signal
              color reserved for urgency, monospace digits so numbers line
              up. It is meant to look more like a Bloomberg terminal than a
              consumer app — because the users are checking it every fifteen
              minutes during a shift.
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

      <section className="section-pad" style={{ borderBottom: "none" }}>
        <div className="container" style={{ textAlign: "center", maxWidth: 720 }}>
          <h2 className="section-title" style={{ fontSize: 36 }}>
            The console is open. Sixty patients are on the floor.
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
