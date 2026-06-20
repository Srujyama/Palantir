# Ontology build runbook — Bottleneck Radar (Foundry Ontology Manager)

Zero-thinking, click-through build. Do the **THIN SLICE** first (Patient, Note,
Bottleneck) and stop — that is enough for a working demo. The **GO FURTHER**
section adds Protocol, ProtocolStep, and Icd10Code.

All source CSVs live in this folder and are already imported as Foundry datasets
with the same name (e.g. dataset `patients` from `patients.csv`). If they are not
imported yet: in Foundry, **Data Connection / Dataset → New dataset → Upload file**,
upload the CSV, then **Apply schema** (let Foundry infer, then fix types per the
tables below). Type names in this runbook use Foundry property types:
`String`, `Integer`, `Timestamp`.

Conventions used below:
- "OM" = Ontology Manager.
- "Object type" creation flow is: **OM → Object Types → New object type**.
- Set each property's **Base type** to match the Type column, and set the
  property API name to exactly the "Foundry property name" given (these names
  match the local backend, so the Pipeline Builder transforms map 1:1).

---

# THIN SLICE — Patient, Note, Bottleneck

## 1. Object type: `Patient`

CSV header (verified): `patient_id,arrival_time,age,sex,chief_complaint`

1. OM → **Object Types → New object type**.
2. Display name: `Patient`. API name: `Patient`.
3. **Description** — paste this literal string (disclosure framing, keep visible):
   > Operational record. Not a clinical record. No PHI.
4. **Backing datasource → Add datasource → Dataset** → select dataset `patients`.
5. **Primary key**: choose column `patient_id`.
6. Add/map properties (Foundry auto-suggests one per column; confirm each):

   | Foundry property name | Type      | Source CSV column  | Notes |
   |-----------------------|-----------|--------------------|-------|
   | `patient_id`          | String    | `patient_id`       | Primary key. e.g. `P-1001`. |
   | `arrival_time`        | Timestamp | `arrival_time`     | ISO string in CSV — set base type Timestamp; Foundry parses ISO. Drives "time on floor". |
   | `age`                 | Integer   | `age`              | |
   | `sex`                 | String    | `sex`              | `M` / `F`. |
   | `chief_complaint`     | String    | `chief_complaint`  | Short free text. |

7. **Title property**: set to `patient_id`.
8. **Description property** (the per-object subtitle, distinct from the object-type
   description in step 3): set to `chief_complaint`.
9. **Save and publish**.

> Do NOT add any link or datasource that brings in eval_labels / ground-truth.
> Those stay dataset-only so the live app cannot read the answer key.

## 2. Object type: `Note`

CSV header (verified): `patient_id,note_text`

1. OM → **New object type**. Display name `Note`, API name `Note`.
2. **Backing datasource → Dataset** → `notes`.
3. **Primary key**: the corpus is 1:1 patient↔note, so use `patient_id` as the
   synthetic `note_id`. Select `patient_id` as the primary key column.
4. Map properties:

   | Foundry property name | Type   | Source CSV column | Notes |
   |-----------------------|--------|-------------------|-------|
   | `patient_id`          | String | `patient_id`      | Primary key here AND FK → `Patient.patient_id`. |
   | `note_text`           | String | `note_text`       | Long text. The CURRENT note. NLP / classifier runs over this. |

5. **Title property**: `patient_id` (no better human label available).
6. **Save and publish**.

## 3. Object type: `Bottleneck` (computed — NO source dataset)

`Bottleneck` has **no CSV**. It is produced by the classifier Function and stored
via writeback. Create it as a **Function-backed / writeback object type**, then
define each property to match the Function's return dict. There is no
column-mapping table here because there are no columns — each non-key property is
filled by the Function output of the same name.

> **CRITICAL — `patient_id` is NOT in the return dict.** The Function signature is
> `classify_bottleneck(note_text, age)` and it returns exactly these 8 keys:
> `category, urgency, owner, protocol_key, evidence_span, summary,
> recommended_action, citation`. There is **no `patient_id` key in the output.**
> The Bottleneck's `patient_id` primary key comes from the **writeback binding
> context** — i.e. the Patient/Note object the Function is invoked against — NOT
> from a returned field. When you wire the Function (step 8 below), bind its
> inputs to the Patient's `Note.note_text` + `Patient.age`, and configure the
> writeback so each result row is keyed by that Patient's `patient_id`. Do not go
> hunting for a `patient_id` return value; it isn't there.

1. OM → **New object type**. Display name `Bottleneck`, API name `Bottleneck`.
2. **Description** — paste this literal string (disclosure framing, keep visible):
   > Operational coordination signal. Surfaces documentation gaps and routes them to the role that handles that coordination work. Not a clinical decision aid; not a diagnostic or therapeutic recommendation.
3. **Backing datasource**: choose an **editable / writeback backing store** (not a
   dataset). The menu wording varies by Foundry version — look for the datasource
   option labelled *Editable*, *Writeback*, or *Edits-only* under **Add
   datasource** (older builds phrase it "object storage v2 / edits only"). This
   gives the object type an editable backing store with no source dataset; the
   classifier Function writes rows into it (one active bottleneck per patient).
   > If your instance does not expose a no-dataset editable backing store, the
   > version-stable fallback is to back `Bottleneck` with a thin writeback dataset
   > (one created/owned by the Function/Logic block) — the materialization in step
   > 8 is identical either way. Do NOT block the demo hunting for an exact button
   > label; any editable/writeback backing store works.
4. **Primary key**: `patient_id` (one active bottleneck per patient).
5. Define properties. The 8 non-key properties each correspond 1:1 to a key in
   the Function's return dict (same name); `patient_id` is the 9th property and is
   the primary key supplied by the binding, NOT a return key (see CRITICAL note).
   Create a property for each row below with the matching name and type:

   | Foundry property name | Type   | Filled from Function return key | Notes |
   |-----------------------|--------|---------------------------------|-------|
   | `patient_id`          | String | *(NOT returned)* — set from writeback binding context | Primary key. FK → `Patient`. Supplied by the binding (the Patient the Function runs against), NOT by a return key. |
   | `category`            | String | `category`                      | One of `awaiting_consult`, `awaiting_imaging`, `dispo_delay`, `missing_soc`, `med_risk`, `readmit_risk`, `clear`. |
   | `urgency`             | String | `urgency`                       | `red` / `amber` / `green`. |
   | `owner`               | String | `owner`                         | Role that handles the coordination work. |
   | `protocol_key`        | String | `protocol_key`                  | Optional FK → `Protocol` (set when rooted in a protocol gap; may be empty). |
   | `evidence_span`       | String | `evidence_span`                 | Substring of the note that triggered it. |
   | `recommended_action`  | String | `recommended_action`            | Imperative next step. This is what Create-Action copies into `Action.title`. |
   | `citation`            | String | `citation`                      | Source guideline when rooted in a protocol/interaction rule (may be empty). |
   | `summary`             | String | `summary`                       | Rationale narrative for the "Why this fired" panel — NOT the Action title. |

6. **Title property**: `recommended_action` (most human-meaningful single field).
7. **Save and publish.**
8. **Wire the Function**: register the classifier as a Function whose output
   schema is this object type, and bind it to write back to the `Bottleneck`
   object set (OM/Functions → the Function's output binding → `Bottleneck`).
   - **Inputs:** the Function takes `note_text` (string) and `age` (integer).
     Bind `note_text` ← the patient's `Note.note_text`, and `age` ← `Patient.age`.
     (`age` is currently unused by the rule cascade but is part of the signature —
     bind it anyway so the call type-checks.)
   - **Key / patient_id:** run the Function per Patient and configure the
     writeback to key each output row by that Patient's `patient_id`. The
     `patient_id` is NOT in the return dict (see the CRITICAL note above) — it is
     established by the binding, so each return dict becomes/updates exactly one
     `Bottleneck` row keyed by the Patient it ran against.

## 4. Link: `Note` → `Patient`

1. OM → **Link Types → New link type** (or open `Patient`, **Links → Add link**).
2. Link name: `note` on Patient / `patient` on Note (pick directional labels).
3. Cardinality: **one-to-one** (one current note per patient in this corpus).
4. Join: `Note.patient_id` = `Patient.patient_id`.
5. **Save and publish.**

> Optional but recommended for the demo: also link `Bottleneck.patient_id` →
> `Patient.patient_id` (one-to-one / 0..1). Same flow as above.

### Thin-slice checkpoint
You now have Patient, Note, Bottleneck, and the Note→Patient link. That is the
minimal working ontology. Stop here unless you want the protocol library and the
ICD lookup.

---

# GO FURTHER — Protocol, ProtocolStep, Icd10Code

## 5. Splitting `protocols.csv` into TWO object types

CSV header (verified):
`protocol_key,protocol_name,time_window_hours,owner,urgency_if_incomplete,citation,trigger_patterns,action_key,action_label,action_documented_patterns,action_severity`

This **one CSV is 47 rows = one row per action** (verified: 47 data rows,
12 distinct `protocol_key` values: `acs aki cap ciwa copd dka gi_bleed
hyperkalemia neutropenic_fever pe sepsis stroke`). The spec wants:

- **`Protocol`** — one row per `protocol_key` (12 rows after dedupe).
- **`ProtocolStep`** — one row per action (all 47 rows, unchanged).

The protocol-level columns (`protocol_name`, `time_window_hours`, `owner`,
`urgency_if_incomplete`, `citation`, `trigger_patterns`) repeat identically on
every action row for a given protocol — that is why Protocol needs a dedupe and
ProtocolStep does not.

### Column ownership

| protocols.csv column          | Goes to `Protocol` | Goes to `ProtocolStep` |
|-------------------------------|:------------------:|:----------------------:|
| `protocol_key`                | yes (PK)           | yes (FK)               |
| `protocol_name`               | yes                | —                      |
| `time_window_hours`           | yes                | —                      |
| `owner`                       | yes                | —                      |
| `urgency_if_incomplete`       | yes                | —                      |
| `citation`                    | yes                | —                      |
| `trigger_patterns`            | yes                | —                      |
| `action_key`                  | —                  | yes (part of PK)       |
| `action_label`                | —                  | yes                    |
| `action_documented_patterns`  | —                  | yes                    |
| `action_severity`             | —                  | yes                    |

### How to materialize the two backing datasets (do this in Pipeline Builder, not OM)

Both object types need a backing dataset. Derive both from `protocols`:

- **`protocols_protocol`** (backs `Protocol`):
  1. Start from `protocols`.
  2. **Select** only: `protocol_key, protocol_name, time_window_hours, owner,
     urgency_if_incomplete, citation, trigger_patterns`.
  3. **Deduplicate / Group by `protocol_key`** (take first of each remaining
     column — they are identical within a key). Result: 12 rows.
  4. Output dataset `protocols_protocol`.

- **`protocols_step`** (backs `ProtocolStep`):
  1. Start from `protocols`.
  2. **Select**: `protocol_key, action_key, action_label,
     action_documented_patterns, action_severity`.
  3. **Add column** `step_id` = concat: `protocol_key + "::" + action_key`
     (formula: `CONCAT(protocol_key, "::", action_key)`). This is the synthesized
     primary key, e.g. `sepsis::antibiotics`.
  4. No dedupe — keep all 47 rows.
  5. Output dataset `protocols_step`.

## 6. Object type: `Protocol`

1. OM → **New object type**. Display `Protocol`, API name `Protocol`.
2. **Backing datasource → Dataset** → `protocols_protocol`.
3. **Primary key**: `protocol_key`.
4. Map properties:

   | Foundry property name     | Type    | Source CSV column        | Notes |
   |---------------------------|---------|--------------------------|-------|
   | `protocol_key`            | String  | `protocol_key`           | PK. One of the 12 keys. |
   | `protocol_name`           | String  | `protocol_name`          | e.g. "Surviving Sepsis Hour-1 Bundle". |
   | `time_window_hours`       | Integer | `time_window_hours`      | |
   | `owner`                   | String  | `owner`                  | In this dataset every protocol is `physician` (the column is single-valued here). |
   | `urgency_if_incomplete`   | String  | `urgency_if_incomplete`  | `red` / `amber` only in this dataset (no `green` rows). |
   | `citation`                | String  | `citation`               | Source guideline. |
   | `trigger_patterns`        | String  | `trigger_patterns`       | Pipe-delimited regex list (keep as one String). |

5. **Title property**: `protocol_name`. **Save and publish.**

## 7. Object type: `ProtocolStep`

1. OM → **New object type**. Display `ProtocolStep`, API name `ProtocolStep`.
2. **Backing datasource → Dataset** → `protocols_step`.
3. **Primary key**: `step_id` (the synthesized column).
4. Map properties:

   | Foundry property name        | Type   | Source CSV column            | Notes |
   |------------------------------|--------|------------------------------|-------|
   | `step_id`                    | String | `step_id` (synthesized)      | PK = `protocol_key + "::" + action_key`. |
   | `protocol_key`               | String | `protocol_key`               | FK → `Protocol`. |
   | `action_key`                 | String | `action_key`                 | e.g. `antibiotics`, `lactate`. |
   | `action_label`               | String | `action_label`               | "Administer broad-spectrum antibiotics". |
   | `action_documented_patterns` | String | `action_documented_patterns` | Pipe-delimited regex list. |
   | `action_severity`            | String | `action_severity`            | All rows are `required` in this dataset (the `recommended` value exists in the schema but no row uses it). |

5. **Title property**: `action_label`. **Save and publish.**

## 8. Link: `ProtocolStep` → `Protocol`

1. OM → **New link type**.
2. Cardinality: **many-to-one** (Protocol 1 ── 1..* ProtocolStep).
3. Join: `ProtocolStep.protocol_key` = `Protocol.protocol_key`.
4. **Save and publish.**

> Optional: link `Bottleneck.protocol_key` → `Protocol.protocol_key`
> (0..1 ── 0..1), used when `Bottleneck.category = missing_soc`.

## 9. Object type: `Icd10Code` (reference lookup)

CSV header (verified): `code,description,category`

1. OM → **New object type**. Display `Icd10Code`, API name `Icd10Code`.
2. **Backing datasource → Dataset** → `icd10_reference`.
3. **Primary key**: `code`.
4. Map properties:

   | Foundry property name | Type   | Source CSV column | Notes |
   |-----------------------|--------|-------------------|-------|
   | `code`                | String | `code`            | PK. e.g. `A41.9`. |
   | `description`         | String | `description`     | e.g. "Sepsis, unspecified organism". |
   | `category`            | String | `category`        | Code family grouping. |

5. **Title property**: `code`. **Description property**: `description`.
6. **Save and publish.**

> This is display/retrieval context only (the ICD candidate rail). It is fine to
> leave it as a plain raw dataset instead of an object type if you don't need it
> linkable — the storyboard wires it as a lookup either way.

---

# What this runbook deliberately omits

- `NoteVersion`, `EvalLabel`, `InteractionFlag`, `Action`, `ActionEvent`,
  `CensusSnapshot`, `HandoffSnapshot` — all "build after the core five" per the
  spec. `EvalLabel` must stay a dataset-only (never an ontology object / never
  linked to Patient) so the live app cannot read ground truth.
