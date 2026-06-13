# Pipeline + Function spec — what to build inside Foundry

Three pieces of compute. The first two go in **Pipeline Builder**, the third
is an **AIP Logic Function** that writes to the `Bottleneck` object set.

---

## Pipeline 1 — Note enrichment

**Inputs**:  `notes` dataset, `icd10_reference` dataset
**Output**:  `note_features` dataset (one row per note)

### Steps
1. **Source**: `notes` (patient_id, note_text)
2. **Use LLM node** — entity extraction.
   System prompt (paste verbatim):
   > You extract structured operational signals from clinical free-text notes
   > for a hospital throughput tool. Output strict JSON. Do not invent values.
   > If a field is not in the note, return null.
   >
   > Schema:
   > {
   >   "vitals": { "BP": "...", "HR": ..., "RR": ..., "SpO2": ..., "Temp": ... },
   >   "labs":   { "WBC": ..., "lactate": ..., "creatinine": ..., "troponin": ..., "glucose": ... },
   >   "consult_requested": "<service or null>",
   >   "consult_acknowledged": true | false,
   >   "imaging_pending": "<modality or null>",
   >   "placement_need": "<SNF/rehab/home/null>",
   >   "isolation_required": true | false,
   >   "explicit_diagnoses": ["..."]
   > }
   User prompt: `{note_text}`

   *Deterministic alternative: port `app/nlp/extractor.py` as a Python
   transform node — this is what the local reference implementation runs,
   and it keeps the enrichment layer LLM-free end to end.*
3. **Use LLM node** — ICD-10 candidate ranking.
   Pass `note_text` + the `icd10_reference` table (description column)
   as context. Ask for the top 5 candidates as a JSON array:
   `[{"code": "R65.20", "score": 0.42}, ...]`
   *Alternative if you want it deterministic: skip the LLM and use a
   TF-IDF transform — Pipeline Builder supports a Python transform node
   for this. The local backend has the working scikit-learn version.*
4. **Output**: `note_features`
   Columns: `patient_id, vitals_json, labs_json, consult_*, imaging_pending,
   placement_need, isolation_required, explicit_diagnoses, icd10_top5_json`

---

## Pipeline 2 — Protocol gap detection

**Inputs**:  `notes`, `protocols` (joined to `ProtocolStep`)
**Output**:  `protocol_gaps` dataset (one row per (patient, protocol, missing_step))

### Steps
1. **Source**: `notes` and `protocols`
2. **Python transform** — paste `pipeline_protocol_gap_transform.py` from
   this folder verbatim. For each (note, protocol) pair it:
   - Finds the first `trigger_patterns` regex match that survives the
     context gates: negation cues suppress only from the LEFT of the
     trigger, clipped to its sentence; historical/resolution cues suppress
     from either side; ambiguous triggers (`CVA`, mild-AKI language) need
     corroborating context elsewhere in the note. If no trigger survives,
     or a per-protocol resolution phrase is present ("anion gap closed",
     "two negative troponins"), skip this protocol for this patient.
   - For each `ProtocolStep` of the matching protocol:
     - Check if any `action_documented_patterns` regex matches `note_text`.
     - If none match → emit a row.
3. **Output schema** (matches `OUTPUT_SCHEMA` in the transform file):
   `patient_id, protocol_key, protocol_name, action_key, action_label,
    action_severity, urgency, owner, citation, trigger_pattern,
    trigger_evidence, trigger_start, trigger_end`

The transform file is GENERATED from `backend/app/protocols/library.py` and
`backend/app/services/silent_failure.py` by `sync_transform.py` — never
edit it by hand; rerun the generator after any rule change. Parity with the
local engine is enforced in CI by `backend/tests/test_foundry_parity.py`,
which (a) re-runs the generator and diffs it against the checked-in file
and (b) asserts field-for-field agreement with `silent_failures()` on all
176 corpus notes.

---

## Function — `classify_bottleneck(note_text, age) → Bottleneck`

Lives as an **AIP Logic / Functions (Python)** function, writing back to the
`Bottleneck` object set.

There is no pseudocode to translate. The complete, executable artifact is
**`aip_logic_classify_bottleneck.py`** in this directory: a self-contained,
stdlib-only port of the full decision path — extraction subset, 12-protocol
silent-failure detector, 13-rule interaction engine, and the cascade with
its two documented policy exceptions (nephrotoxic-flag subsumption into a
triggered AKI workup; red interaction flags with objective harm evidence
outranking equal-urgency protocol gaps). Its module docstring covers
Functions-repo registration and writeback shape.

Decision path, in priority order (each branch fully implemented in the
artifact):

1. `missing_soc` — highest-urgency protocol gap, owner from the protocol
2. `med_risk` — top interaction flag (severity → urgency, pharmacist)
3. `awaiting_consult` → physician, `awaiting_imaging` → nurse
4. `readmit_risk`, then `dispo_delay` → case manager
5. `clear`

Parity with the local engine is enforced by
`backend/tests/test_aip_logic_parity.py`: all 176 corpus notes must produce
the identical (category, urgency, owner) triple as
`backend/app/services/bottleneck.py`. If a rule changes locally, that test
names the diverging patients until the artifact is re-frozen.
Use Function bindings to expose this so Workshop can re-run on demand.

---

## What runs where (the safe answer for the demo)

| Step                                | Runs in                         |
|-------------------------------------|---------------------------------|
| Note → entities, ICD-10 candidates  | Pipeline Builder LLM node       |
| Note → protocol gaps                | Pipeline Builder Python transform |
| Patient → Bottleneck                | AIP Logic Function (deterministic) |
| User clicks "Create action"         | Action type / Workshop button   |
| User clicks "Why stuck?"            | AIP Logic Function returning the same evidence + cited protocol |

**No LLM is in the path that produces a recommendation.** The LLM is only
used to extract structured signals from text. Recommendations come from
deterministic protocol-gap rules. This is the right line to hold for the
clinical-decision-aid restriction.
