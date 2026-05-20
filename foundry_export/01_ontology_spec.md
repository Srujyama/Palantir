# Ontology spec — Bottleneck Radar in Foundry

This is what to create in **Ontology Manager** before opening Pipeline Builder.
The names match the local backend so the pipeline transforms map 1:1.

---

## Object types

### `Patient`
Source dataset: `patients.csv`
Primary key: `patient_id`

| Property            | Type      | Notes                                             |
|---------------------|-----------|---------------------------------------------------|
| `patient_id`        | string    | Primary key. e.g. `P-1001`                        |
| `arrival_time`      | timestamp | ISO. Drives "time on floor" calculations.         |
| `age`               | integer   |                                                   |
| `sex`               | string    | `M` / `F`                                         |
| `chief_complaint`   | string    | Short free text                                   |
| `expected_owner`    | string    | Held-out label. Don't surface in the live UI.     |

**Title property**: `patient_id`
**Description property**: `chief_complaint`

---

### `Note`
Source dataset: `notes.csv`
Primary key: synthetic `note_id` (use `patient_id` since it's 1:1 in this corpus)

| Property      | Type     |
|---------------|----------|
| `patient_id`  | string   | FK → `Patient.patient_id`                         |
| `note_text`   | string   | Long text. Will run NLP over this.                |

**Link**: `Note.patient_id` → `Patient.patient_id`  (one-to-one in this corpus)

---

### `Protocol`
Source dataset: `protocols.csv` (collapse to one row per protocol_key)
Primary key: `protocol_key`

| Property                   | Type    | Notes                                                |
|----------------------------|---------|------------------------------------------------------|
| `protocol_key`             | string  | `sepsis`, `acs`, `stroke`, `cap`, `dka`              |
| `protocol_name`            | string  | "Surviving Sepsis Hour-1 Bundle"                     |
| `time_window_hours`        | integer |                                                      |
| `owner`                    | string  | `physician` / `pharmacist` / `nurse` / `case_manager`|
| `urgency_if_incomplete`    | string  | `red` / `amber` / `green`                            |
| `citation`                 | string  | The source guideline                                 |
| `trigger_patterns`         | string  | Pipe-delimited regex list                            |

---

### `ProtocolStep`
Source dataset: `protocols.csv` (one row per action)
Primary key: synthesize `step_id = protocol_key + "::" + action_key`

| Property                     | Type    |
|------------------------------|---------|
| `step_id`                    | string  | PK                                                   |
| `protocol_key`               | string  | FK → `Protocol`                                      |
| `action_key`                 | string  | e.g. `antibiotics`, `lactate`                        |
| `action_label`               | string  | "Administer broad-spectrum antibiotics"              |
| `action_documented_patterns` | string  | Pipe-delimited regex list                            |
| `action_severity`            | string  | `required` / `recommended`                           |

**Link**: `ProtocolStep.protocol_key` → `Protocol.protocol_key`  (many-to-one)

---

### `Bottleneck` (computed by Function — not in source data)
Primary key: `patient_id` (one active bottleneck per patient)

| Property        | Type    |
|-----------------|---------|
| `patient_id`    | string  | FK → `Patient`                                       |
| `category`      | string  | `awaiting_consult`, `awaiting_imaging`, `dispo_delay`, `missing_soc`, `med_risk`, `readmit_risk`, `clear` |
| `urgency`       | string  | `red` / `amber` / `green`                            |
| `owner`         | string  |                                                      |
| `protocol_key`  | string  | Optional FK → `Protocol` if rooted in a protocol gap |
| `evidence_span` | string  | Substring of the note that triggered it             |
| `summary`       | string  | "Documentation gap, standard-of-care step"           |

---

### `Action` (workflow object — created by Workshop button click)
Primary key: `action_id` (uuid)

| Property        | Type      |
|-----------------|-----------|
| `action_id`     | string    | PK                                                   |
| `patient_id`    | string    | FK                                                   |
| `title`         | string    | The recommended next coordination step               |
| `owner_role`    | string    |                                                      |
| `status`        | string    | `open` / `in_progress` / `resolved` / `escalated`    |
| `created_at`    | timestamp |                                                      |
| `bottleneck_category` | string |                                                  |

---

## Relationships summary

```
Patient (1) ── (1) Note
Patient (1) ── (0..1) Bottleneck
Patient (1) ── (0..*) Action
Protocol (1) ── (1..*) ProtocolStep
Bottleneck (0..1) ── (0..1) Protocol     [optional, when category = missing_soc]
```

---

## Disclosure framing (keep visible)

In the Ontology description fields, type these literal strings — they protect
the Use Case Restriction position:

- `Patient.description`: *"Operational record. Not a clinical record. No PHI."*
- `Bottleneck.description`: *"Operational coordination signal. Surfaces documentation
  gaps and routes them to the role that handles that coordination work. Not
  a clinical decision aid; not a diagnostic or therapeutic recommendation."*
