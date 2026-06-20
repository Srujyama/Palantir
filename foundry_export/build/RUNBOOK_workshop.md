# Workshop build runbook — THIN SLICE (zero-thinking)

Two screens: **Queue** and **Patient detail**. Goal: assemble fast, read on
camera like the local React app. Follow top to bottom. Skip nothing in the
"BUILD" sections; the "OPTIONAL, build later" callouts are explicitly safe to
skip for the thin slice.

**Prereq objects that must exist before you start** (from `01_ontology_spec.md`):
`Patient`, `Note`, `Protocol`, `ProtocolStep`, `Bottleneck` (Function-computed).
`Action` is OPTIONAL for the thin slice — the queue + patient + bottleneck story
stands without writeback. `NoteVersion`, `InteractionFlag`, `CensusSnapshot`,
`HandoffSnapshot`, `Icd10Code` are all OPTIONAL.

Property names below are copied verbatim from the ontology spec — bind to these
exact strings.

### STEP 0 — Populate the `Bottleneck` object set for ALL patients (DO THIS FIRST)

> **This is the single most common way the demo fails on camera.** `Bottleneck`
> has no source dataset — it is materialized ONLY when the `classify_bottleneck`
> Function runs and writes back (see `RUNBOOK_ontology.md` §3 step 8). The Function
> wrapper (`function_repo/function.py`) is a **per-patient** invocation. Nothing in
> the thin slice triggers it for the whole census, because the automation that
> normally does that (`05_automations_spec.md` Automation (c) — hourly backstop)
> is marked OPTIONAL below. **If you skip that automation AND skip this step, the
> `Bottleneck` object set is empty: every KPI card reads 0, and every table row
> shows a blank urgency pill / category / recommended_action.** The screen looks
> broken on camera.

Before building any widget, run a ONE-TIME backfill so all 176 `Bottleneck` rows
exist. Pick whichever is fastest in your stack:

- **Easiest:** create Automation (c) from `05_automations_spec.md` (object monitor
  on `Note` + scheduled backstop) and **manually run it once** ("Run now"). It
  invokes `classify_bottleneck` for each patient and upserts one `Bottleneck`
  keyed on `patient_id`.
- **Or batch-invoke directly:** in a Function/Pipeline or the Functions test
  console, map over the `Patient` object set and call
  `classify_bottleneck_fn(note_text = linked Note.note_text, age = Patient.age)`
  for every patient, writing each result back to `Bottleneck` keyed on that
  patient's `patient_id`.

**Verify before continuing:** open the `Bottleneck` object set in OM/Object
Explorer and confirm the row count is ~176 (not 0, not 1) and that `urgency`
holds a mix of `red`/`amber`/`green`. Only then build the widgets below — every
aggregation and the table depend on this set being full.

---

## SCREEN 1 — Queue

Route: `/dashboard` (Workshop module: name it `Queue`).

### Variables to declare first (Workshop Variables panel)

| Variable name        | Type            | Default | Used by                          |
|----------------------|-----------------|---------|----------------------------------|
| `v_urgency`          | string          | `all`   | Patient table filter             |
| `v_owner`            | string          | `all`   | Patient table filter             |
| `v_category`         | string          | `all`   | Patient table filter             |
| `v_search`           | string          | (empty) | Patient table free-text filter   |

Declare these BEFORE building widgets so the table's filter clauses can reference
them.

### Widget 1 — Header strip (Text widgets, no binding)

- Title text: `Bottleneck Radar · Floor 3 East · Operational Coordination`
- Badge text (smaller, muted): `Operational coordination tool. Not a clinical decision aid.`

No data binding. Pure layout. Keep it — it sets the frame on camera.

### Widget 2 — KPI row (six Metric Card widgets)

Each card = one Workshop **Metric Card**, value bound to an **object-set
aggregation**. Build the object set inline on each card.

| # | Card label        | Object set                                   | Aggregation |
|---|-------------------|----------------------------------------------|-------------|
| 1 | In census         | `Patient` (all)                              | `count()` → `count(Patient)` |
| 2 | Critical          | `Bottleneck` filtered `urgency == "red"`     | `count()` → `count(Bottleneck where urgency=="red")` |
| 3 | Elevated          | `Bottleneck` filtered `urgency == "amber"`   | `count()` → `count(Bottleneck where urgency=="amber")` |
| 4 | Routine           | `Bottleneck` filtered `urgency == "green"`   | `count()` → `count(Bottleneck where urgency=="green")` |
| 5 | Silent failures   | `Bottleneck` filtered `category != "clear"` AND rooted in a protocol gap (proxy for `protocol_gaps`) | `count()` |
| 6 | Open actions      | `Action` filtered `status == "open"`         | `count()` → `count(Action where status=="open")` |

Notes for zero-thinking:
- Cards 1–4 are the load-bearing ones. Build these four first.
- Card 5 ("Silent failures"): the storyboard writes this as `count(protocol_gaps)`,
  but `protocol_gaps` (Pipeline 2 output) has **one row per (patient, protocol,
  missing_step)** — counting it gives the number of missing STEPS, which is larger
  than the patient count and does NOT match the demo narration ("~56 patients with
  documentation gaps"). For a per-PATIENT count that matches the narration, bind
  `count(Bottleneck where category=="missing_soc")` instead (≈52 on this corpus).
  This is the recommended binding on camera — it is also simpler because it needs
  no extra object set. Only use a literal `count(protocol_gaps)` if you have
  promoted `protocol_gaps` to an object set AND your narration is about steps, not
  patients.
- Card 6 ("Open actions"): if you skip the `Action` object (thin slice), bind
  this card to a literal `0` or hide it. The story still reads. Mark it
  **OPTIONAL** in your build.

### Widget 3 — Filter bar (four input widgets, top of table)

| Control            | Widget type        | Bind to     | Options |
|--------------------|--------------------|-------------|---------|
| Urgency            | Dropdown / Button group | `v_urgency`  | `red`, `amber`, `green`, `all` |
| Owner              | Dropdown           | `v_owner`   | `physician`, `nurse`, `pharmacist`, `case_manager`, `all` |
| Bottleneck category| Dropdown           | `v_category`| `awaiting_consult`, `awaiting_imaging`, `dispo_delay`, `missing_soc`, `med_risk`, `readmit_risk`, `clear`, `all` |
| Search             | Text input         | `v_search`  | free text over `patient_id` + `chief_complaint` |

THIN-SLICE shortcut: if time is tight, ship only **Urgency** + **Search**. Those
two carry the demo. Owner and category dropdowns are nice-to-have.

### Widget 4 — Patient table (Object Table widget) — THE CENTERPIECE

- **Object set:** `Patient`, with `Bottleneck` joined via the
  `Patient (1) ── (0..1) Bottleneck` link (link on `patient_id`).
- **Filters (apply the variables):**
  - if `v_urgency != "all"` → `Bottleneck.urgency == v_urgency`
  - if `v_owner != "all"` → `Bottleneck.owner == v_owner`
  - if `v_category != "all"` → `Bottleneck.category == v_category`
  - if `v_search` non-empty → `Patient.patient_id contains v_search` OR
    `Patient.chief_complaint contains v_search`
- **Columns (left to right):**

| Header                   | Source property                       |
|--------------------------|---------------------------------------|
| (urgency pill)           | `Bottleneck.urgency` rendered as colored pill (red/amber/green) |
| Patient                  | `Patient.patient_id`                  |
| Age/Sex                  | `Patient.age` + `Patient.sex`         |
| LOS                      | computed from `Patient.arrival_time` (now − arrival, in h) |
| Bottleneck category      | `Bottleneck.category`                 |
| Recommended coordination | `Bottleneck.recommended_action`       |
| Owner                    | `Bottleneck.owner`                    |
| Open actions             | `count(Action where patient_id==row.patient_id && status=="open")` — **OPTIONAL**; show blank/0 if no `Action` object |

- **Row click → navigation:** on row select, **navigate to the `Patient detail`
  module**, passing `patient_id = selectedRow.Patient.patient_id` as the path /
  module input param (`p_patient_id`). This is the single most important wiring
  on the screen — verify it works before anything else.

### Widget 5 — Footer (Text widget, no binding) — OPTIONAL

Citation block + `All cases notional. No PHI.` + the Use Case Restriction line.
Drop it if pressed for time; the badge in the header already covers disclosure.

---

## SCREEN 2 — Patient detail

Route: `/p/{patient_id}` (Workshop module: `Patient detail`).
**Module input variable:** `p_patient_id` (string) — received from the Queue
row click. Every object set below is filtered to this one patient.

Two-column layout: left = main, right = rail.

### Scoping object sets

- `thisPatient` = `Patient where patient_id == p_patient_id` (single object).
- `thisBottleneck` = `Bottleneck where patient_id == p_patient_id` (0..1).
- `thisNote` = `Note where patient_id == p_patient_id` (single).

### LEFT COLUMN

#### L1 — Header (Text/Metric widgets bound to `thisPatient`)
- `thisPatient.patient_id`
- `thisPatient.age` + `thisPatient.sex`
- "arrived Xh ago" computed from `thisPatient.arrival_time`
- urgency pill from `thisBottleneck.urgency`

#### L2 — Bottleneck card (bound to `thisBottleneck`) — CORE

| Field shown            | Bind to                         |
|------------------------|---------------------------------|
| Category               | `thisBottleneck.category`       |
| Urgency                | `thisBottleneck.urgency`        |
| Owner                  | `thisBottleneck.owner`          |
| Recommended coordination | `thisBottleneck.recommended_action` |
| Citation               | `thisBottleneck.citation`       |
| Summary / "Why this fired" | `thisBottleneck.summary` (rationale narrative) in an expand panel; quote `thisBottleneck.evidence_span` inside it as the evidence span |

Do NOT put `summary` where `recommended_action` goes and vice versa —
`recommended_action` is the imperative step; `summary` is the rationale.

#### L3 — Patient note (Text widget, monospace, bound to `thisNote.note_text`)
Render `note_text` as monospace. THIN SLICE: plain render is fine. The
trigger-span highlighting (compute via Function) is **OPTIONAL, build later**.

#### L4 — Care-pathway evaluation table (Object Table)
- **Source:** the `protocol_gaps` for this patient. In the thin slice, drive
  this from the `ProtocolStep` rows of the protocol named in
  `thisBottleneck.protocol_key`, joined `ProtocolStep.protocol_key →
  Protocol.protocol_key`.
- **Columns:**

| Header        | Source                                              |
|---------------|-----------------------------------------------------|
| Protocol      | `Protocol.protocol_name`                             |
| Status        | gaps N (or N/A) — N = count of missing required steps |
| Documented    | green check for steps satisfied                     |
| Missing       | red dot for steps not documented (`action_label`)   |

One row per protocol that triggered. If wiring the full gap computation is slow,
THIN-SLICE fallback: show the single protocol from `thisBottleneck.protocol_key`
with its steps from `ProtocolStep.action_label` and mark the one named in
`recommended_action` as Missing. Reads correctly on camera.

#### L5 — Trajectory panel — **OPTIONAL, build later**
Bound to `NoteVersion` rows + current `Note`. Narrative only; never changes the
category. Skip for the thin slice.

#### L6 — Workflow actions — **OPTIONAL, build later** (see Action wiring below)

### RIGHT RAIL

#### R1 — Snapshot KV (key-value widget, bound to `thisBottleneck`) — CORE
- Owner → `thisBottleneck.owner`
- Category → `thisBottleneck.category`
- Open SF (silent failures) → 1 if `category=="missing_soc"` else 0 (proxy)
- Open actions → `count(Action where patient_id==p_patient_id && status=="open")`
  — **OPTIONAL**; show 0 if no `Action` object.

#### R2 — ICD-10 candidates — **OPTIONAL, build later**
Top 5 from `note_features.icd10_top5_json`. Skip for thin slice.

#### R3 — Extracted entities (vitals/labs/meds chips) — **OPTIONAL, build later**
From `note_features` JSON. Skip for thin slice.

#### R4 — "Why is this patient stuck?" button — **OPTIONAL, build later**
Re-runs the Function in a side panel. Skip for thin slice — L2's "Why this fired"
expand already delivers the cited-evidence beat.

---

## ACTION WIRING — "Create action" button — **OPTIONAL for thin slice**

The queue + patient + bottleneck story stands without writeback. Build this only
if you have time after both screens read clean. Mark the `Action` object OPTIONAL.

Button: **+ Create action from recommendation** → invoke Action Type
`create-coordination-action`.

- **Parameters:**
  - `patient_id` ← `p_patient_id`
  - `title` ← `thisBottleneck.recommended_action` (the imperative step — NOT
    `summary`/`rationale`)
  - `owner_role` ← `thisBottleneck.owner`
  - `bottleneck_category` ← `thisBottleneck.category`
- **Side effect:** writes a new `Action` row with `status = "open"` and
  `created_at = now()`.

Start / Resolve / Escalate (three more Action Types mutating only
`Action.status`) are also **OPTIONAL, build later**. So is `finalize-handoff`.

Demo trade-off: if you skip `Action`, in the demo script step 4 ("I create the
coordination ticket… board now shows one open action") simply gesture at the
`recommended_action` + `owner` on the card instead of clicking. The narrative
still lands.

---

## MINIMUM VIABLE ON CAMERA (<90s) — build THIS first

If you build only the following, you can tell the whole story in under 90
seconds and it reads like the local app. Everything else is gravy.

> **Before any of this, do STEP 0 at the top of this file** — backfill the
> `Bottleneck` object set for all patients. With an empty Bottleneck set the KPI
> cards and the whole table render blank, even if every widget is wired correctly.

**Screen 1 (Queue):**
1. Header strip (title + disclaimer badge).
2. Four KPI cards: In census `count(Patient)`, Critical
   `count(Bottleneck where urgency=="red")`, Elevated (amber), Silent failures
   `count(Bottleneck where category=="missing_soc")`.
3. Patient table: columns = urgency pill, `patient_id`, bottleneck `category`,
   `recommended_action`, `owner`. **Row click → Screen 2 passing `patient_id`.**
4. Urgency + Search filters only.

**Screen 2 (Patient detail):**
5. Header (patient_id, age/sex, urgency pill).
6. Bottleneck card: `category`, `urgency`, `owner`, `recommended_action`,
   `citation`, and the "Why this fired" expand showing `summary` +
   `evidence_span`.
7. Patient note (monospace `note_text`).
8. Right-rail Snapshot KV: owner + category.

That's it. Skip: Action writeback, trajectory, interactions, ICD-10 rail,
entity chips, "why stuck" panel, footer, owner/category dropdowns,
care-pathway table (or use the single-protocol fallback if you have 5 extra
minutes — it strengthens the "specific missing step" beat).

**The one thing that must work:** row-click navigation from the table to the
patient detail screen carrying `patient_id`. Test that before recording.
