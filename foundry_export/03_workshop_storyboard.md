# Workshop application storyboard

Two screens. Match the local React app so the demo video reads as one product.

---

## Screen 1 — Queue (`/`)

**Layout** (Workshop sections, top to bottom):

1. **Header strip** — title "Bottleneck Radar · Floor 3 East · Operational Coordination"
   + small badge: *"Operational coordination tool. Not a clinical decision aid."*

2. **KPI row** — six metric cards.
   Each card is a Workshop Metric component bound to an aggregation:
   - In census  →  `count(Patient)`
   - Critical   →  `count(Bottleneck where urgency == "red")`
   - Elevated   →  `count(Bottleneck where urgency == "amber")`
   - Routine    →  `count(Bottleneck where urgency == "green")`
   - Silent failures → `count(protocol_gaps)`
   - Open actions    → `count(Action where status == "open")`

3. **Filter bar** — Workshop variable inputs:
   - Urgency filter (red / amber / green / all)
   - Owner filter (physician / nurse / pharmacist / case_manager / all)
   - Bottleneck category filter
   - Free-text search over `patient_id` and `chief_complaint`

4. **Patient table** — Object Table component, source = `Patient` joined
   with `Bottleneck`. Columns:
   `urgency pill | patient_id | age/sex | LOS | bottleneck category | recommended coordination | owner | open actions count`

   Row click → navigate to Screen 2 with `patient_id` as a path param.

5. **Footer** — citation block with the 12 protocol citations + "All cases
   notional. No PHI." + the Use Case Restriction disclosure repeated.

---

## Screen 2 — Patient detail (`/p/{patient_id}`)

Two-column layout.

### Left column (main)

1. **Header**: `patient_id`, age/sex, "arrived Xh ago", urgency pill.
2. **Bottleneck card** — bound to the single `Bottleneck` for this patient.
   Shows: category, urgency, owner, recommended coordination, citation,
   "Why this fired" → expand panel with the evidence span quoted.
3. **Patient note** — render `note_text` as monospace; highlight any spans
   that matched a trigger pattern (compute via Function).
4. **Care-pathway evaluation table** — for each Protocol that triggered:
   protocol name | status (gaps N or N/A) | documented (green ✓) |
   missing (red ●). One row per protocol from `protocol_gaps`.
5. **Trajectory panel** — bound to the patient's prior `Note` versions
   (oldest-first) plus the current note. Shows per-lab trend lines
   (lactate clearing vs. creatinine worsening), recurrent-admission cues,
   and a green **"gaps closed across notes"** block: protocol steps that
   were missing in an earlier note but documented by now. This is the
   *done-and-resolved* signal that keeps the board from nagging about a
   step already charted. It is **narrative only** — the `classify_bottleneck`
   Function reads only the current note, never the priors, so the
   trajectory never changes the category. In Foundry it is a read-only
   Function over the `Note` link set, not an input to classification.
6. **Workflow actions** — list of `Action` objects for this patient.
   Buttons:
   - **+ Create action from recommendation** → triggers an Action object
     with `title = bottleneck.summary`, `owner_role = bottleneck.owner`.
   - Each existing Action row: Start / Resolve / Escalate buttons that
     mutate `Action.status`.

### Right rail

1. **Snapshot KV** — owner, category, open SF, open actions.
2. **ICD-10 candidates** — top 5 from `note_features.icd10_top5_json`,
   shown as code + description + score.
3. **Extracted entities** — vitals chips, labs chips, meds chips
   from `note_features` JSON columns.
4. **"Why is this patient stuck?"** button → opens a side panel that
   re-runs the bottleneck Function and shows headline + 2-3 cited bullets.

---

## Action wiring

In Workshop, the "Create action" button is an **Action Type** invocation:
- Action type: `create-coordination-action`
- Parameters: `patient_id`, `title`, `owner_role`, `bottleneck_category`
- Side effect: writes a new row to the `Action` object set with
  `status = "open"` and `created_at = now()`.

The Start / Resolve / Escalate buttons are three more Action Types, each
mutating only `Action.status`. Keep them tightly scoped — Workshop reviewers
look for clean, named actions over generic edits.

---

## Snapshots — giving the board memory

A live board forgets; an ops record can't. Two writes-as-objects mirror
the local `census`/handoff snapshot helpers:

- **Finalize handoff** — an Action Type `finalize-handoff` that freezes
  the current shift-handoff roll-up into a new immutable `HandoffSnapshot`
  object (`shift_label`, `finalized_by`, `captured_at`, frozen payload).
  Retrieve it later by id — "the handoff given at 19:00 last night." It is
  append-only: the Action never mutates an existing snapshot.
- **Census snapshot** — a scheduled Automation (or the demo's LIVE TICK)
  writes a `CensusSnapshot` row (occupancy, red/amber/green mix, open and
  overdue actions, silent-failure count). A Workshop Time Series chart over
  that object set gives the KPI strip a real trend line instead of one
  instantaneous number.

Both are raw object writes with no clinical content — the same read-only
posture the rest of the app holds toward the `Patient` record.

---

## Demo script (90 seconds, fits the < 4-min video)

1. *(Landing)* "Hospital ops teams already know which patients are slow.
   They don't know which specific coordination step is missing for each
   one. That's what this finds." — click Enter.
2. *(Queue)* "176 patients, 44 critical, 56 with documentation gaps
   against published care pathways. Each row tells me what's missing
   and which role on the floor handles it." — point at the SF column.
3. *(P-1001 detail)* "This patient has a documented sepsis bundle
   triggered by the SIRS span in the note, but the antibiotics line
   isn't documented yet. The system surfaces that as a coordination
   gap. The clinical decision is still the physician's — we're just
   making sure it doesn't fall off the board."
4. *(Click Create action)* "I create the coordination ticket, route it
   to physician on duty. The board now shows one open action."
5. *(Back to queue)* "Same pipeline runs on every patient, every shift,
   with full audit trail back to the note span and the cited protocol."

---

## What NOT to do in Workshop

- Don't add an LLM chat panel that suggests treatment.
- Don't surface "diagnosis" or "treatment recommendation" as labels —
  use "ICD-10 candidate" and "coordination signal".
- Don't let a Function write to the `Patient` object (read-only).
- Don't ingest any external real data; AIP Now is for notional/dev only.

---

## Order of operations once your AIP workspace is live

1. Create a Foundry **Project** named `bottleneck-radar`.
2. Upload the five CSVs from this folder into a `raw/` folder in the project
   (run `python build_csvs.py` first to regenerate them from the backend).
3. Build the Ontology object types per `01_ontology_spec.md`.
4. Wire `patients.csv` → `Patient`, `notes.csv` → `Note`, `protocols.csv`
   → `Protocol` + `ProtocolStep`, `icd10_reference.csv` → `Icd10Code`.
   Leave `eval_labels.csv` as a raw dataset — it is the held-out answer
   key and must not back any ontology object the app can read.
5. Build Pipeline 1 (note enrichment) and Pipeline 2 (gap detection)
   per `02_pipeline_and_function_spec.md`. Pipeline 2's Python node is
   `pipeline_protocol_gap_transform.py`, generated by `sync_transform.py`
   and parity-tested against the local engine on all 176 notes.
6. Author the Function `classify_bottleneck` and bind it to `Patient`.
7. Build the Workshop app in two screens per this storyboard.
8. Record the 90-second narration over a screen capture, post unlisted
   to YouTube, send to recruiter.
