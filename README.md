# Bottleneck Radar

> Operational coordination tool for hospital throughput. Not a clinical
> decision aid. All clinical judgment remains with the care team.

Built for the Palantir AIP build challenge. Reads the same notes a charge
nurse already reads, surfaces — in one screen — which documented step is
missing for each patient, and routes the coordination action to the role
on the floor that handles that kind of work.

---

## What it actually is

For every patient on the floor, the console answers five questions:

| Question                            | How it answers                                                  |
| ----------------------------------- | --------------------------------------------------------------- |
| Which patients are stuck right now? | Cascading rule classifier ranks each patient into one of 7 categories. |
| Why is that patient stuck?          | Quotes the exact span of the note that triggered the signal.    |
| Which protocol step is missing?     | Matches the note against 12 published care pathways.            |
| Which med combinations need a pharmacist? | 13 citation-backed interaction rules over the extracted med list. |
| Who owns the next coordination?     | Physician / Nurse / Pharmacist / Case manager.                  |

No LLM is anywhere in this pipeline. Extraction is deterministic regex
plus a NegEx-lite negation pass; recommendations come from
deterministic protocol-gap rules with named citations. In a Foundry
deployment, AIP's LLM tooling could assist entity extraction upstream —
but the recommendation path stays rule-based and auditable. That is the
right line to hold for the AIP Use Case Restriction on clinical
decision aids.

---

## Eight screens, one pipeline

The same data backs every screen.

| Route          | View              | What it shows                                                  |
| -------------- | ----------------- | -------------------------------------------------------------- |
| `/`            | Landing           | Editorial overview. The CTA is "Enter the operations console." |
| `/dashboard`   | Queue             | Every patient, ranked by urgency. Filter, search, bulk-route.  |
| `/floor`       | Floor map         | Spatial view of all 180 beds across 6 wings, colored by urgency. |
| `/analytics`   | Analytics         | Cohort-level metrics: gap distribution, owner load, LOS buckets, census-over-time trend — plus the live model card. |
| `/capacity`    | Capacity / What-If | 48h bed-census forecast + scenario builder: resolve a bottleneck group, see beds freed by when. |
| `/sandbox`     | Triage sandbox    | Paste any note, watch the 4-stage pipeline run with evidence highlighting and per-stage timings. |
| `/handoff`     | Shift handoff     | Printable artifact for shift change. Built for paper — and can be finalized into an immutable snapshot. |
| `/p/{id}`      | Patient detail    | Note + evidence + protocol table + interaction flags + actions + timeline + trajectory (longitudinal trend across prior notes). |

---

## The pipeline

```
note text
   │
   ▼
[1] Entity extractor  (+ NegEx-lite negation pass)
   │  vitals, labs, meds (with class), consults (pending?),
   │  imaging (pending?), dispo blockers, symptoms, code status,
   │  mobility, pain, advance directives, social context, risk factors.
   │  Negated findings ("denies melena") are tagged, never dropped.
   ▼
[2] Protocol matcher
   │  12 care pathways. For each, check: did its trigger fire? (left-
   │  context negation + historical-cue handling, so "ruled out for ACS"
   │  doesn't trigger the ACS pathway) — then for each expected action,
   │  is there a documented pattern? otherwise emit a "silent failure".
   ▼
[3] Drug-interaction screen
   │  13 citation-backed rules over the extracted med list + lab/symptom
   │  context. Negation-aware. Flags already covered by a triggered
   │  protocol's expected actions are subsumed, not double-counted.
   ▼
[4] Bottleneck cascade
   │  missing_soc → med_risk → awaiting_consult → awaiting_imaging
   │  → readmit_risk → dispo_delay → clear. One policy exception: a red
   │  interaction flag with objective harm evidence in the note (e.g.
   │  anticoagulation + documented melena) outranks an equal-urgency
   │  protocol gap.
   ▼
classified patient + actions + audit trail

   ┄┄ in parallel, display-only ┄┄
[*] ICD-10 retriever
      TF-IDF + cosine over a 39-code reference of high-acuity codes,
      clinical abbreviations expanded before vectorizing. Retrieval
      context for the UI rail only — the decision path never consumes it.
```

The ICD-10 retriever runs alongside the decision path purely to populate
the candidate-codes rail; classification completes without it. Keeping it
out of the recommendation path is deliberate — it's display context, not
an input to any rule.

Each step is inspectable on the patient detail page, and the whole trace
is interactive on `/sandbox`. The note panel highlights the spans the
matcher fired on. The protocol table shows which expected steps were
documented and which are missing. The "Why stuck?" panel composes the
rationale from those primitives.

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

Triggers carry clinical gates, not just keywords: sepsis auto-triggers
on lactate ≥ 4 even without the word "sepsis", AKI requires KDIGO-grade
severity, ACS respects rule-out language ("two negative troponins"),
stroke knows when the tPA window has expired, COPD recognizes
resolution phrasing. Adding a thirteenth pathway is a config change,
not a code change.

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

## Medication safety as data

The `med_risk` category is backed by a declarative interaction engine
(`app/services/interactions.py`): 13 rules, each naming the drug classes
it fires on, the lab or symptom context it requires, a one-sentence
mechanism, a pharmacist-voiced recommendation, and a literature
citation. Rules range from the classics (anticoagulant + NSAID, opioid +
benzodiazepine, the "triple whammy") to context-gated ones
(anticoagulation + documented GI bleed, insulin + recorded
hypoglycemia, warfarin + supratherapeutic INR). The engine is
negation-aware — "denies melena" never satisfies a bleed-context rule —
and brand names normalize to generics so "enoxaparin (Lovenox)" can't
satisfy a two-drug rule against itself. A flag that a triggered
protocol already covers (nephrotoxic combo during an active AKI workup)
is subsumed into that protocol's gap rather than double-counted.

Flags surface on the patient page (`GET /patients/{id}/interactions`)
with the involved meds, the recommendation, and the citation.

---

## Closing the loop

Surfacing a bottleneck is half the job; the other half is making sure
somebody acts before the window closes. Every coordination action gets
an SLA deadline from an explicit policy table (`app/services/sla.py`) —
ops-owned data, not a model:

| Source category, urgency  | SLA     | Derivation                                  |
| ------------------------- | ------- | ------------------------------------------- |
| `missing_soc`, red        | 60 min  | 1h bundles: sepsis, stroke, neutropenic fever, hyperkalemia |
| `missing_soc`, amber      | 240 min | 4–6h bundles (COPD, CAP); conservative bound |
| `med_risk`, red           | 60 min  | Active patient-safety exposure              |
| `med_risk`, amber         | 120 min | Safety review within a nursing shift block  |
| `awaiting_consult`, any   | 240 min | Page + 30-min escalation ladder, ×2 retries |
| `awaiting_imaging`, any   | 180 min | Radiology expedite window                   |
| `readmit_risk`, any       | 720 min | Transitional-care setup, half a day         |
| `dispo_delay`, any        | 1440 min | Placement / auth work, one business day    |
| anything else             | 480 min | Default: one 8h shift                       |

Actions move through an explicit state machine (`open → in_progress →
resolved / escalated`, with a reopen path), and every transition, note,
and SLA breach writes an `ActionEvent` audit row with the acting user.
A breach sweep (`POST /actions/sweep`) escalates everything past its
deadline and logs `sla_breach` events. The queue shows per-patient
`OVERDUE` badges; each action card shows its countdown chip and
escalation level; the audit trail is one click away. In Foundry, the
sweep is an Automation and the policy table is a versioned object set a
throughput lead can tune without touching code.

---

## Deciding before acting

`/capacity` answers the bed-manager question: *if we cleared this class
of blocker, how many beds do we actually get back, and when?*

`GET /capacity/forecast` projects the 48-hour census from a
deterministic residual-LOS model: base residual hours per bottleneck
category, urgency and age modifiers, a 08:00–20:00 discharge window,
and arrival rates measured from the corpus. `POST /capacity/simulate`
re-runs the same model with a chosen bottleneck group resolved and
reports the freed beds at 6/12/24/48h checkpoints, plus the named
patients whose discharge moves. On the demo corpus, resolving every
`dispo_delay` bottleneck frees **+32 beds within 24 hours** — all 32
dispo-delayed patients discharge earlier (run inside the discharge
window; an overnight anchor shifts the same 32 beds onto the next
morning's schedule). There is no ML and no randomness here: every
number traces to a stated assumption, and the full assumptions table is
returned in every response and rendered on the page.

---

## Measured, not asserted

The corpus ships with held-out truth labels, and the classifier is
scored against them continuously — in the API (`GET /eval/summary`,
`GET /eval/misses`), on the `/analytics` model card, and in the tuning
harness (`tools/eval_harness.py`):

- **Primary-category accuracy: 100% (176/176 labeled notes).** Honest
  framing: the corpus has 4 generated notes per template, so this means
  all 44 bottleneck templates are handled — it is not evidence of
  robustness to arbitrary paraphrase. The `/sandbox` page exists so you
  can test that yourself.
- **Owner routing: 90.9% (160/176).** The 16 misses are a documented
  labeling inconsistency, not a hidden bug: the spec routes
  `awaiting_imaging` to the nurse, but 4 imaging templates in the
  synthetic corpus were labeled `physician`. We left the data as-is and
  documented the conflict — honesty over vanity metrics.
- **Regression gate:** `tests/test_sandbox_eval.py` re-classifies the
  full corpus inside the test suite and fails any rule change that
  drops accuracy below 0.97. Rule edits are tuned with
  `tools/eval_harness.py`, which clusters misses by template with the
  classifier's own rationale.

---

## Trajectory — telling never-done from done-and-resolved

A single note is a snapshot. The patient detail page also reads the
patient's prior notes (oldest-first) and composes a *trajectory*
narrative (`app/services/trends.py`, surfaced in the `trends` block of
`GET /patients/{id}` and rendered by `TrajectoryPanel`): which labs are
rising or falling and whether that is clinically improving or worsening
(lactate clearing vs. creatinine climbing), recurrent-admission cues,
and the green **"gaps closed across notes"** block — protocol steps that
were missing in an earlier note but are documented by now.

That last capability is the operational point: it distinguishes a step
that was *never done* (a real bottleneck) from one that was *done and
resolved* (no action needed), so the board doesn't nag a charge nurse
about antibiotics that are already charted. The resolved-gap rule is
deliberately strict — the protocol must still trigger in the current
note and the specific action must have moved out of its missing set; a
protocol that simply stops firing because the presentation changed is
*not* counted as resolved, because that would be a dangerous false
reassurance.

**Narrative only, by construction.** Trajectory is a display/coordination
signal. The classifier (`app/services/bottleneck.classify`) never sees
prior notes — it reads only the current `note_text` (see the design
invariant at the top of `trends.py` and §3 of the model card). History
changes the story the console tells, not the decision the rules make, so
the corpus eval stays 1.0 *by construction* rather than by tuning. On
P-1002, for example, the panel reads lactate 4.1 → 3.6 → 3.1 (clearing),
creatinine 1.4 → 1.7 → 1.9 (worsening), and two Surviving Sepsis bundle
steps (blood cultures, crystalloid) closed across notes — without any of
that touching the category the engine assigns.

---

## Floor memory — census-over-time + finalized handoffs

A live dashboard forgets. Two small persistence helpers
(`app/services/census.py`, `app/api/census.py`) give the console memory:

- **Census snapshots.** `capture_census` freezes a floor-wide roll-up
  (occupancy, red/amber/green acuity mix, open and overdue actions,
  silent-failure count); the LIVE TICK captures one automatically.
  `GET /census/series` returns the time series so `/analytics` can draw a
  real census/acuity trend line instead of a single instantaneous
  number.
- **Finalized handoffs.** `POST /census/handoff/finalize` freezes the
  current handoff report into an immutable artifact (`HandoffSnapshot`)
  retrievable later by id — "the handoff given at 19:00 last night" —
  the auditable record a live page can't be. `GET /census/handoff/history`
  lists them; `GET /census/handoff/{id}` returns one exactly as frozen.

---

## Provability — the auditability guarantee, mechanically enforced

"Verifiable, not a black box" is the thesis, so it is made *checkable at
runtime* rather than asserted. The provenance export
(`app/services/audit.py`, `GET /audit/patient/{id}`,
`GET /audit/corpus/summary`) re-derives every surfaced signal's chain of
custody — signal → recommended action → guideline citation → evidence
span(s) — and re-checks the auditability invariant against each
patient's own note:

```
note_text[start:end] == span.text   →   verified == True
```

On the live corpus the export reports **404 / 404 evidence spans verify
(100%, zero offenders)** across all 176 patients — the highlight a
clinician sees *is* the text the rule fired on, byte for byte. Citation
coverage is **67.09%** corpus-wide (212 of 316 signals), and that is
correct *by design*: every `missing_soc` and `med_risk` signal carries a
literature citation, while purely operational categories
(`awaiting_consult`, `awaiting_imaging`, `dispo_delay`, `readmit_risk`)
carry none — there is no guideline to cite for "page cardiology." Among
guideline-derived signals, citation coverage is 100%.

The guarantee is backed by tests, not just an endpoint: a property test
(`tests/test_properties.py`) pins determinism (same note → same
category/urgency/owner) and span integrity; adversarial fuzzing
(`tests/test_fuzz_notes.py`) proves the pipeline never crashes and never
emits an invalid span under mutation; `tests/test_audit.py` asserts the
corpus-wide `pct_verified == 100.0` with an empty offender list. The
full reasoning lives in `backend/docs/MODEL_CARD.md`.

---

## Architecture

```
palantir/
├── backend/                     FastAPI + SQLite
│   ├── app/
│   │   ├── api/                 patients, actions, stats, floor, analytics,
│   │   │                        handoff, capacity, sandbox, interactions,
│   │   │                        evaluation, simulate, census, audit
│   │   ├── data/                synthetic note generator + ICD-10 reference
│   │   ├── db/                  SQLAlchemy + session factory
│   │   ├── models/              ORM + Pydantic schemas
│   │   ├── nlp/                 entity extractor (NegEx-lite) + ICD-10 TF-IDF matcher
│   │   ├── protocols/           library of 12 care pathways
│   │   └── services/            bottleneck cascade, silent-failure detector,
│   │                            SLA policy, capacity model, interaction engine,
│   │                            longitudinal trends, census/handoff snapshots,
│   │                            provenance/audit export, eval harness
│   ├── tests/                   pytest suite (382 tests covering all layers)
│   ├── tools/                   eval_harness.py — offline rule-tuning loop
│   └── requirements.txt
├── frontend/                    React + TypeScript + Vite
│   ├── src/
│   │   ├── components/          PatientTable, FloorMap, Timeline, CommandPalette, ...
│   │   ├── lib/                 API client + formatters
│   │   ├── pages/               Landing, Queue, Patient, Floor, Analytics,
│   │   │                        Capacity, Sandbox, Handoff
│   │   ├── styles/              global.css + per-page css
│   │   └── types/               API type definitions
│   └── package.json
├── foundry_export/              the Foundry/AIP port kit
│   ├── 01_ontology_spec.md      object types, properties, links
│   ├── 02_pipeline_and_function_spec.md   transforms + AIP Logic functions
│   ├── 03_workshop_storyboard.md          the console screens in Workshop
│   ├── pipeline_protocol_gap_transform.py self-contained pipeline transform
│   ├── build_csvs.py / upload_csvs.py     dataset build + upload tooling
│   ├── patients.csv · notes.csv · protocols.csv · icd10_reference.csv
│   ├── eval_labels.csv          held-out truth — raw dataset only, never an
│   │                            ontology object the app reads
│   └── ...                      plus parity/sync tooling and further specs —
│                                see foundry_export/
└── README.md                    you are here
```

### Backend stack

- **FastAPI** REST API with typed Pydantic schemas
- **SQLite** as a stand-in for a Foundry ontology
- **scikit-learn** TF-IDF + cosine similarity for ICD-10 retrieval
- **Pure-Python regex** rule engine for the protocol matcher,
  negation tagging, and interaction screening
- **SQLAlchemy ORM** with `Patient`, `Triage`, `Action`, `ActionEvent`
  (audit), `NoteVersion` (prior notes for trajectory), `CensusSnapshot`,
  and `HandoffSnapshot` tables
- **pytest** suite, 382 tests (incl. property, fuzz, and audit-invariant
  tests), runs in under twenty seconds; full pipeline classifies a note
  in single-digit milliseconds
- **Provability layer** — `app/services/audit.py` + `GET /audit/*`
  re-verify every evidence span against its note
  (`note_text[start:end] == span.text`); the full method and reproduction
  commands are in `backend/docs/MODEL_CARD.md`

### Frontend stack

- **React 18 + TypeScript + Vite**
- Dark, dense, monospace-digit UI for the console
- Light editorial design for the landing page
- No external UI kit, no charting library — every visualization
  (census step chart included) is plain SVG / divs
- Command palette (`⌘K`), keyboard shortcuts (`g`+letter), bulk select with `x`
- **TrajectoryPanel** (longitudinal lab trends + sparklines + the
  "gaps closed across notes" block) on the patient detail page
- **StoryMode** — a guided, keyboard-driven demo tour (`★ STORY` in the
  titlebar, the command palette, or `Shift+S`) that walks the whole
  product as one narrated story: queue → P-1002 drill-down → trajectory →
  sandbox → capacity → model card → analytics → floor. The script lives
  as data in `src/lib/storyScript.ts`; `→`/Space advance, `Esc` exits,
  `p` auto-plays.
- Titlebar extras: a **LIVE TICK** button (`POST /simulate/tick` —
  seeded, deterministic admits/discharges/action progress so the floor
  visibly moves during a demo, and which also captures a census snapshot)
  and a real API-latency health badge

---

## Running locally

**Fastest path — one command:**

```bash
./run-demo.sh        # picks free ports, ingests data on first run, opens on :5173
```

`run-demo.sh` starts the backend on the first free port at/above 8001, points
the frontend's `/api` proxy at it, waits until the API answers, and prints the
URL to open. Ctrl-C stops both. Use this for recording — it sidesteps the
common case where another local app is squatting on port 8000.

**Manual path:**

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m app.data.generate_notes   # generate the 176-note corpus
python -m app.ingest                # build DB and run pipeline on every note
uvicorn app.main:app --reload --port 8000   # use --port 8001 if 8000 is busy

# Frontend (separate terminal)
cd frontend
npm install
npm run dev                          # http://localhost:5173
# if the backend is on 8001:
RADAR_API=http://localhost:8001 npm run dev

# Tests
cd backend
python -m pytest tests/ -v

# Eval harness (corpus accuracy + miss clusters)
python tools/eval_harness.py
```

The Vite dev server proxies `/api` to `http://localhost:8000`, or to
`$RADAR_API` when set.

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
- **Not a prediction product.** The capacity model is a planning
  calculator with stated assumptions, not a forecast of clinical
  outcomes.
- **Not a medical device.** For demonstration only.

---

## Foundry / AIP port

`foundry_export/` contains everything to lift the same pipeline into
AIP:

- five CSVs for the raw layer (`build_csvs.py` regenerates,
  `upload_csvs.py` pushes to the Foundry datasets) — including
  `eval_labels.csv`, the held-out answer key kept as a raw dataset that
  is never linked into the ontology the app reads
- ontology object specs (Patient, Note, Protocol, ProtocolStep,
  Bottleneck, Action)
- the self-contained Python transform for the protocol-gap pipeline,
  with the deterministic classifier expressed as an AIP Logic function
- a Workshop storyboard for the console screens
- parity and sync tooling so the Foundry transform and the local
  backend can be checked against each other on the same corpus

See `foundry_export/01_ontology_spec.md` and friends, and
`foundry_export/06_demo_video_script.md` for the demo narrative.

---

## Data

All 176 patients in the corpus are notional, generated from 44
templates (4 notes each) that encode realistic bottleneck patterns. No
PHI. No real chart text. Names are obviously synthetic (`P-1042`).
Truth labels ship with the corpus for evaluation and are never surfaced
in the operational UI.

The same pipeline runs unchanged against real notes in a Foundry
deployment with the appropriate ontology, sign-off, and safety controls.
