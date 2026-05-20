# Bottleneck Radar

> Operational coordination tool for hospital throughput. Not a clinical
> decision aid. All clinical judgment remains with the care team.

Built for the Palantir AIP build challenge. Reads the same notes a charge
nurse already reads, surfaces — in one screen — which documented step is
missing for each patient, and routes the coordination action to the role
on the floor that handles that kind of work.

---

## What it actually is

For every patient on the floor, the console answers four questions:

| Question                            | How it answers                                                  |
| ----------------------------------- | --------------------------------------------------------------- |
| Which patients are stuck right now? | Cascading rule classifier ranks each patient into one of 7 categories. |
| Why is that patient stuck?          | Quotes the exact span of the note that triggered the signal.    |
| Which protocol step is missing?     | Matches the note against 12 published care pathways.            |
| Who owns the next coordination?     | Physician / Nurse / Pharmacist / Case manager.                  |

No LLM is in the path that produces a recommendation. The optional LLM
sits in entity extraction. Recommendations come from deterministic
protocol-gap rules with named citations. That is the right line to hold
for the AIP Use Case Restriction on clinical decision aids.

---

## Five views, one pipeline

The same data backs every screen.

| Route          | View              | What it shows                                                  |
| -------------- | ----------------- | -------------------------------------------------------------- |
| `/`            | Landing           | Editorial overview. The CTA is "Enter the operations console." |
| `/dashboard`   | Queue             | Every patient, ranked by urgency. Filter, search, bulk-route.  |
| `/floor`       | Floor map         | Spatial view of all 180 beds across 6 wings, colored by urgency. |
| `/analytics`   | Analytics         | Cohort-level metrics: gap distribution, owner load, LOS buckets. |
| `/handoff`     | Shift handoff     | Printable artifact for shift change. Built for paper.          |
| `/p/{id}`      | Patient detail    | Note + evidence + protocol table + actions + timeline.         |

---

## The pipeline

```
note text
   │
   ▼
[1] Entity extractor
   │  vitals, labs, meds (with class), consults (pending?),
   │  imaging (pending?), dispo blockers, symptoms, code status,
   │  mobility, pain, advance directives, social context, risk factors
   ▼
[2] ICD-10 retriever
   │  TF-IDF + cosine over a 39-code reference of high-acuity codes
   ▼
[3] Protocol matcher
   │  12 care pathways. For each, check: did its trigger fire? for
   │  each expected action, is there a documented pattern? otherwise
   │  emit a "silent failure" row.
   ▼
[4] Bottleneck cascade
   │  missing_soc → med_risk → awaiting_consult → awaiting_imaging
   │  → readmit_risk → dispo_delay → clear
   ▼
classified patient + actions + audit trail
```

Each step is inspectable on the patient detail page. The note panel
highlights the spans the matcher fired on. The protocol table shows
which expected steps were documented and which are missing. The "Why
stuck?" panel composes the rationale from those primitives.

---

## Protocol library

Twelve published care pathways are encoded as data — triggers, expected
actions, owner, urgency-if-incomplete, time window, citation.

| Protocol                        | Window | Citation                                |
| ------------------------------- | ------ | --------------------------------------- |
| Surviving Sepsis Hour-1 Bundle  | 1h     | Surviving Sepsis Campaign               |
| NSTEMI / Unstable Angina        | 2h     | ACC/AHA Guidelines                      |
| Acute Ischemic Stroke / tPA     | 1h     | AHA/ASA Guidelines                      |
| Community-Acquired Pneumonia    | 6h     | IDSA/ATS Guidelines                     |
| Diabetic Ketoacidosis           | 2h     | ADA DKA Guidelines                      |
| Pulmonary Embolism              | 2h     | ESC/AHA PE Guidelines                   |
| Upper GI Bleed                  | 2h     | ACG Guidelines                          |
| Acute Kidney Injury Workup      | 12h    | KDIGO AKI Guidelines                    |
| Alcohol Withdrawal (CIWA)       | 2h     | ASAM Guidelines                         |
| Neutropenic Fever               | 1h     | IDSA Febrile Neutropenia                |
| Severe Hyperkalemia             | 1h     | ESC/AHA Consensus                       |
| COPD Exacerbation               | 4h     | GOLD Strategy                           |

Adding a thirteenth is a config change, not a code change.

---

## Bottleneck taxonomy

Seven mutually exclusive categories, owner attached. Cascade order is
the priority: patient safety dominates, then workflow blockers, then
dispo holds.

| Category                          | Owner          | Example                                                            |
| --------------------------------- | -------------- | ------------------------------------------------------------------ |
| `missing_soc` Missing standard-of-care step | Physician   | Sepsis bundle triggered, antibiotics not documented.               |
| `med_risk` Medication safety risk | Pharmacist     | DOAC + NSAID + active bleed signals.                               |
| `awaiting_consult` Awaiting specialist consult | Physician | Hip fx, ortho consult requested 14h ago, no callback.              |
| `awaiting_imaging` Awaiting imaging | Nurse        | RLQ pain, CT abd ordered 5h ago, in queue.                         |
| `readmit_risk` High readmission risk | Case manager | Third DKA in 8 months, no PCP follow-up.                           |
| `dispo_delay` Discharge / placement delay | Case manager | Medically ready, SNF declined, insurance auth pending.             |
| `clear` No active bottleneck      | —              | Tracked, not surfaced.                                             |

---

## Architecture

```
palantir/
├── backend/                     FastAPI + SQLite
│   ├── app/
│   │   ├── api/                 patients, actions, stats, floor, analytics, handoff
│   │   ├── data/                synthetic note generator + ICD-10 reference
│   │   ├── db/                  SQLAlchemy + session factory
│   │   ├── models/              ORM + Pydantic schemas
│   │   ├── nlp/                 entity extractor + ICD-10 TF-IDF matcher
│   │   ├── protocols/           library of 12 care pathways
│   │   └── services/            bottleneck cascade, silent-failure detector
│   ├── tests/                   pytest suite (48 tests covering all layers)
│   └── requirements.txt
├── frontend/                    React + TypeScript + Vite
│   ├── src/
│   │   ├── components/          PatientTable, FloorMap, Timeline, CommandPalette, ...
│   │   ├── lib/                 API client + formatters
│   │   ├── pages/               Landing, Queue, Patient, Floor, Analytics, Handoff
│   │   ├── styles/              global.css + landing.css
│   │   └── types/               API type definitions
│   └── package.json
├── foundry_export/              CSVs + Pipeline Builder transforms + AIP spec docs
│   ├── 01_ontology_spec.md
│   ├── 02_pipeline_and_function_spec.md
│   ├── 03_workshop_storyboard.md
│   ├── pipeline_protocol_gap_transform.py
│   ├── build_csvs.py
│   ├── upload_csvs.py
│   ├── patients.csv             (176 patients)
│   ├── notes.csv                (176 notes)
│   ├── protocols.csv            (47 protocol-action rows)
│   └── icd10_reference.csv      (39 codes)
└── README.md                    you are here
```

### Backend stack

- **FastAPI** REST API with typed Pydantic schemas
- **SQLite** as a stand-in for a Foundry ontology
- **scikit-learn** TF-IDF + cosine similarity for ICD-10 retrieval
- **Pure-Python regex** rule engine for the protocol matcher
- **SQLAlchemy ORM** with `Patient`, `Triage`, `Action`, `ActionEvent` (audit) tables
- **pytest** suite, 48 tests, runs in under 2 seconds

### Frontend stack

- **React 18 + TypeScript + Vite**
- Dark, dense, monospace-digit UI for the console
- Light editorial design for the landing page
- No external UI kit, no charting library — every visualization is plain SVG / divs
- Command palette (`⌘K`), keyboard shortcuts (`g`+letter), bulk select with `x`

---

## Running locally

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.data.generate_notes   # generate the 176-note corpus
python -m app.ingest                # build DB and run pipeline on every note
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173

# Tests
cd backend
python -m pytest tests/ -v
```

The Vite dev server proxies `/api` to `http://localhost:8000`.

---

## What it isn't

- **Not a clinical decision aid.** It does not provide diagnoses,
  treatment recommendations, or medical advice. Every signal is an
  operational coordination signal: a documented step is missing, a
  consult hasn't been acked, a placement is pending. The clinician
  decides what to do.
- **Not a chatbot.** No LLM generates clinical text.
- **Not a chart writer.** It does not modify the patient record. The
  console is read-only against the ontology.
- **Not a medical device.** For demonstration only.

---

## Foundry / AIP port

`foundry_export/` contains everything to lift the same pipeline into
AIP:

- four CSVs for the raw layer
- ontology object specs (Patient, Note, Protocol, ProtocolStep,
  Bottleneck, Action)
- the self-contained Python transform for the protocol-gap pipeline
- the function spec for `classify_bottleneck`
- a Workshop storyboard for the two console screens

See `foundry_export/01_ontology_spec.md` and friends.

---

## Data

All 176 patients in the corpus are notional, generated from 27
templates that encode realistic bottleneck patterns. No PHI. No real
chart text. Names are obviously synthetic (`P-1042`).

The same pipeline runs unchanged against real notes in a Foundry
deployment with the appropriate ontology, sign-off, and safety controls.
