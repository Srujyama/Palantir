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
2. **Python transform** — for each (note, protocol) pair:
   - Check if any `trigger_patterns` regex matches `note_text`.
     If none match, skip this protocol for this patient.
   - For each `ProtocolStep` of the matching protocol:
     - Check if any `action_documented_patterns` regex matches `note_text`.
     - If none match → emit a row.
3. **Output schema**:
   `patient_id, protocol_key, protocol_name, action_key, action_label,
    urgency, owner, citation, evidence_trigger_span`

This is a direct port of `backend/app/services/silent_failure.py`.

---

## Function — `classify_bottleneck(patient_id) → Bottleneck`

Lives as an **AIP Logic Function** on the `Patient` object type.

### Pseudocode

```python
def classify_bottleneck(patient: Patient) -> Bottleneck:
    note    = patient.note            # via link
    feats   = note_features[patient.patient_id]
    gaps    = protocol_gaps.filter(patient_id == patient.patient_id)

    # priority order — first match wins
    if gaps.any(urgency == "red"):
        g = gaps.filter(urgency == "red").first()
        return Bottleneck(
            category      = "missing_soc",
            urgency       = "red",
            owner         = g.owner,
            protocol_key  = g.protocol_key,
            evidence_span = g.evidence_trigger_span,
            summary       = f"Documented step missing on {g.protocol_name}: {g.action_label}",
        )

    if feats.consult_requested and not feats.consult_acknowledged:
        hours_waiting = now() - patient.arrival_time
        urgency = "red" if hours_waiting > 12 else "amber"
        return Bottleneck(
            category      = "awaiting_consult",
            urgency       = urgency,
            owner         = "physician",
            evidence_span = f"{feats.consult_requested} consult requested",
            summary       = f"Awaiting {feats.consult_requested} consult, {hours_waiting:.0f}h",
        )

    if feats.imaging_pending:
        return Bottleneck("awaiting_imaging", "amber", "physician", evidence_span=feats.imaging_pending,
                          summary=f"Awaiting {feats.imaging_pending}")

    if feats.placement_need and hours_on_floor(patient) > 24:
        return Bottleneck("dispo_delay", "amber", "case_manager",
                          evidence_span=feats.placement_need,
                          summary=f"Placement gap: {feats.placement_need}")

    if has_med_risk_pattern(feats.labs, feats.explicit_diagnoses):
        return Bottleneck("med_risk", "amber", "pharmacist", ...)

    if has_readmit_signals(patient, note):
        return Bottleneck("readmit_risk", "amber", "case_manager", ...)

    if gaps.any(urgency == "amber"):
        ...

    return Bottleneck("clear", "green", owner=None, summary="No active bottleneck")
```

The local backend has the full working version at
`backend/app/services/bottleneck.py` — translate the rules straight across.
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
