"""
Pipeline Builder — Python transform: protocol-gap detection.

Self-contained. Paste this whole file into a Pipeline Builder Python transform
node. The protocol library and the negation rules are inlined so there are no
imports beyond pyspark and the standard library.

Inputs (two Foundry datasets, joined by patient_id):
  - notes:       columns [patient_id (string), note_text (string)]
  - protocols:   not used at runtime — kept in source control for traceability
                 and for re-derivation if rules change. The rules below are
                 the source of truth for this transform.

Output dataset:
  protocol_gaps — one row per (patient, triggered protocol, missing step)

Output schema:
  patient_id              string
  protocol_key            string   sepsis | acs | stroke | cap | dka
  protocol_name           string
  action_key              string
  action_label            string   "Administer broad-spectrum antibiotics"
  action_severity         string   required | recommended
  urgency                 string   red | amber | green
  owner                   string   physician | pharmacist | nurse | case_manager
  citation                string   "Surviving Sepsis Campaign Hour-1 Bundle (2018)"
  trigger_pattern         string   the regex that triggered the protocol
  trigger_evidence        string   the literal substring of the note
  trigger_start           integer  char offset in note_text
  trigger_end             integer  char offset in note_text

If a protocol triggers but every expected step is documented, no rows are
emitted for that (patient, protocol).  If a protocol does not trigger, no
rows.  If the protocol is triggered but a resolution phrase is present, no
rows.

Author: ported from backend/app/services/silent_failure.py.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterator, List, Optional

# Pipeline Builder injects pyspark — import lazily so this file is also
# runnable as a unit test outside Foundry.
try:
    from pyspark.sql import DataFrame, SparkSession
    from pyspark.sql.types import (
        ArrayType, IntegerType, StringType, StructField, StructType,
    )
except Exception:  # pragma: no cover — only happens when running locally
    DataFrame = SparkSession = None  # type: ignore


# ---------------------------------------------------------------------------
# Protocol library — frozen copy of backend/app/protocols/library.py
# Keep this in sync when rules change. The list IS the rule engine.
# ---------------------------------------------------------------------------

PROTOCOLS: List[Dict[str, Any]] = [
    {
        "key": "sepsis",
        "name": "Surviving Sepsis Hour-1 Bundle",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 1,
        "citation": "Surviving Sepsis Campaign Hour-1 Bundle (2018)",
        "triggers": [
            r"\bsepsis\b", r"\bseptic\b", r"\bSIRS\b",
            r"lactate\s*[>:]?\s*[2-9]",
            r"hypotension", r"\bMAP\b\s*<", r"BP\s*\d{2}/\d{2}",
        ],
        "actions": [
            {
                "key": "lactate", "severity": "required",
                "label": "Measure serum lactate",
                "documented": [r"\blactate\b\s*\d", r"lactate\s+drawn", r"lactate\s+result"],
            },
            {
                "key": "blood_cx", "severity": "required",
                "label": "Draw blood cultures before antibiotics",
                "documented": [r"blood\s+culture", r"\bBCx\b"],
            },
            {
                "key": "antibiotics", "severity": "required",
                "label": "Administer broad-spectrum antibiotics",
                "documented": [
                    r"\b(antibiotic|antibiotics|abx)\b\s*(given|started|administered|initiated|ordered)",
                    r"\b(vancomycin|piperacillin|tazobactam|cefepime|meropenem|ceftriaxone|zosyn|cefazolin|levofloxacin|azithromycin|ciprofloxacin)\b",
                ],
            },
            {
                "key": "fluids", "severity": "required",
                "label": "Begin 30 mL/kg crystalloid resuscitation",
                "documented": [r"30\s*mL/kg", r"fluid\s+bolus", r"IV\s+fluids?\s+(initiated|bolus|running)"],
            },
        ],
    },
    {
        "key": "acs",
        "name": "NSTEMI / Unstable Angina Initial Management",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 2,
        "citation": "ACC/AHA NSTEMI Guidelines",
        "triggers": [
            r"\bNSTEMI\b", r"\bSTEMI\b", r"\bACS\b",
            r"chest\s+(pain|pressure|tightness)\b.*(troponin|ECG|EKG)",
            r"troponin\s+(I\s+)?(elevated|positive|\d+\.\d+)",
            r"ST\s*(depression|elevation)",
        ],
        "actions": [
            {
                "key": "asa", "severity": "required",
                "label": "Aspirin 162-325 mg given",
                "documented": [r"\bASA\b\s*(\d+\s*(mg)?)?\s*(given|administered|chewed)", r"aspirin\s+\d"],
            },
            {
                "key": "anticoag", "severity": "required",
                "label": "Anticoagulation (heparin or LMWH)",
                "documented": [r"\b(heparin|enoxaparin|lovenox|fondaparinux)\b"],
            },
            {
                "key": "cards_consult", "severity": "required",
                "label": "Cardiology consult",
                "documented": [r"cardiology\s+(consult|notified|aware|to\s+see)"],
            },
            {
                "key": "serial_trop", "severity": "required",
                "label": "Serial troponin / ECG monitoring",
                "documented": [r"repeat\s+(troponin|ECG|EKG)", r"serial\s+(troponin|ECG)", r"telemetry"],
            },
        ],
    },
    {
        "key": "stroke",
        "name": "Acute Ischemic Stroke / tPA Window",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 1,
        "citation": "AHA/ASA Acute Ischemic Stroke Guidelines",
        "triggers": [
            r"\bstroke\b", r"\bCVA\b", r"hemiparesis", r"hemiplegia",
            r"\bNIHSS\b", r"aphasi[ac]", r"facial\s+droop", r"last\s+known\s+well",
        ],
        "actions": [
            {
                "key": "ct_head", "severity": "required",
                "label": "Non-contrast head CT",
                "documented": [r"head\s+CT", r"CT\s+head", r"non-?contrast\s+CT"],
            },
            {
                "key": "neuro_consult", "severity": "required",
                "label": "Neurology consult / stroke team activation",
                "documented": [
                    r"neurology\s+(consult|notified|aware|to\s+see)",
                    r"stroke\s+(team|alert|code)\s+(activated|called|notified)",
                ],
            },
            {
                "key": "tpa_eval", "severity": "required",
                "label": "tPA / thrombolytic eligibility evaluation",
                "documented": [r"\btPA\b", r"alteplase", r"thrombolytic", r"thrombectomy"],
            },
            {
                "key": "bp_control", "severity": "required",
                "label": "Blood pressure control",
                "documented": [r"BP\s+control", r"nicardipine", r"labetalol", r"antihypertensive"],
            },
        ],
    },
    {
        "key": "cap",
        "name": "Community-Acquired Pneumonia Initial Management",
        "owner": "physician",
        "urgency": "amber",
        "time_window_hours": 6,
        "citation": "IDSA/ATS Community-Acquired Pneumonia Guidelines",
        "triggers": [
            r"community-?acquired\s+pneumonia", r"\bCAP\b\b",
            r"pneumonia.*CURB",
            r"\bpneumonia\b.*(consolidation|infiltrate)",
        ],
        "actions": [
            {
                "key": "antibiotics", "severity": "required",
                "label": "Empiric antibiotics within 6h of arrival",
                "documented": [
                    r"\b(ceftriaxone|azithromycin|levofloxacin|moxifloxacin|doxycycline|amoxicillin)\b",
                    r"\bantibiotics?\s+(given|started|administered)",
                ],
            },
            {
                "key": "blood_cx", "severity": "recommended",
                "label": "Blood cultures if severe",
                "documented": [r"blood\s+culture", r"\bBCx\b"],
            },
            {
                "key": "o2_assessment", "severity": "required",
                "label": "Oxygenation assessed (SpO2 or ABG)",
                "documented": [r"SpO2", r"\bABG\b", r"oxygen\s+saturation"],
            },
        ],
    },
    {
        "key": "dka",
        "name": "Diabetic Ketoacidosis Management",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 2,
        "citation": "ADA DKA Management Guidelines",
        "triggers": [
            r"\bDKA\b", r"diabetic\s+ketoacidosis",
            r"anion\s+gap\s+\d{2}", r"beta-?hydroxybutyrate",
            r"glucose\s*[>:]?\s*[3-9]\d{2}",
        ],
        "actions": [
            {
                "key": "insulin", "severity": "required",
                "label": "Insulin infusion initiated",
                "documented": [r"insulin\s+(drip|infusion|bolus|started)", r"\b0\.1\s*units?/kg"],
            },
            {
                "key": "fluids", "severity": "required",
                "label": "IV fluid resuscitation",
                "documented": [r"IV\s+fluids?", r"normal\s+saline", r"\bNS\b\s+(bolus|running)"],
            },
            {
                "key": "k_replace", "severity": "required",
                "label": "Potassium repletion if K < 5.3",
                "documented": [r"potassium\s+(repletion|replacement|added)", r"\bKCl\b", r"K\s+\d"],
            },
            {
                "key": "monitor_gap", "severity": "required",
                "label": "Serial anion gap / electrolytes",
                "documented": [r"repeat\s+(labs|BMP|chem|gap)", r"serial\s+(labs|gap|electrolytes)"],
            },
        ],
    },
]


# ---------------------------------------------------------------------------
# Context / negation rules — frozen from silent_failure.py
# ---------------------------------------------------------------------------

NEGATION_TOKENS = [
    "resolved", "denies", "no ", "not ", "improving", "improved",
    "ruled out", "history of", "h/o", "prior", "previous",
    "stable", "negative", "without", "afebrile",
    "admitted", "days ago", "weeks ago", "last admission",
    "post-op", "post op", "second admission", "third admission",
]
NEGATION_WINDOW = 60

PROTOCOL_RESOLUTION_PHRASES: Dict[str, List[str]] = {
    "dka":    [r"DKA\s+resolved", r"anion\s+gap\s+closed", r"gap\s+closed", r"bicarbonate\s+(2[0-9]|[3-9]\d)"],
    "sepsis": [r"sepsis\s+resolved", r"afebrile\s+for"],
    "stroke": [r"stroke\s+resolved", r"deficits\s+resolved"],
    "cap":    [r"pneumonia\s+(resolved|improving)"],
    "acs":    [r"chest\s+pain\s+resolved", r"troponin\s+down-?trending"],
}

# Trigger patterns whose literal match is too ambiguous on its own; require
# at least one corroborating keyword anywhere in the note before firing.
AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT: Dict[str, List[str]] = {
    r"\bCVA\b": ["stroke", "infarct", "tPA", "NIHSS", "hemiparesis", "aphasi", "facial droop"],
}


# ---------------------------------------------------------------------------
# Pure-Python core (no Spark dependency) — also used for unit tests
# ---------------------------------------------------------------------------

def _is_negated_or_historical(note: str, start: int, end: int) -> bool:
    left = note[max(0, start - NEGATION_WINDOW): start].lower()
    right = note[end: end + NEGATION_WINDOW].lower()
    window = left + " " + right
    return any(tok in window for tok in NEGATION_TOKENS)


def _ambiguous_trigger_passes(note: str, pattern: str) -> bool:
    needs = AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT.get(pattern)
    if not needs:
        return True
    lowered = note.lower()
    return any(kw.lower() in lowered for kw in needs)


def _protocol_resolved(note: str, proto_key: str) -> bool:
    for pat in PROTOCOL_RESOLUTION_PHRASES.get(proto_key, []):
        if re.search(pat, note, flags=re.IGNORECASE):
            return True
    return False


def _find_first_trigger(note: str, patterns: List[str]) -> Optional[Dict[str, Any]]:
    """First trigger that is neither historical/negated nor ambiguous-without-context."""
    for pat in patterns:
        for m in re.finditer(pat, note, flags=re.IGNORECASE):
            if _is_negated_or_historical(note, m.start(), m.end()):
                continue
            if not _ambiguous_trigger_passes(note, pat):
                continue
            return {
                "pattern": pat,
                "evidence": m.group(0),
                "start": m.start(),
                "end": m.end(),
            }
    return None


def _any_match(note: str, patterns: List[str]) -> bool:
    return any(re.search(p, note, flags=re.IGNORECASE) for p in patterns)


def detect_gaps_for_note(patient_id: str, note: str) -> List[Dict[str, Any]]:
    """Return one dict per (triggered protocol, missing step) for this note."""
    rows: List[Dict[str, Any]] = []
    if not note:
        return rows

    for proto in PROTOCOLS:
        trig = _find_first_trigger(note, proto["triggers"])
        if not trig:
            continue
        if _protocol_resolved(note, proto["key"]):
            continue

        for action in proto["actions"]:
            if _any_match(note, action["documented"]):
                continue  # documented — not a gap
            rows.append({
                "patient_id":       patient_id,
                "protocol_key":     proto["key"],
                "protocol_name":    proto["name"],
                "action_key":       action["key"],
                "action_label":     action["label"],
                "action_severity":  action["severity"],
                "urgency":          proto["urgency"],
                "owner":            proto["owner"],
                "citation":         proto["citation"],
                "trigger_pattern":  trig["pattern"],
                "trigger_evidence": trig["evidence"],
                "trigger_start":    trig["start"],
                "trigger_end":      trig["end"],
            })
    return rows


# ---------------------------------------------------------------------------
# Pipeline Builder entry point
# ---------------------------------------------------------------------------

OUTPUT_SCHEMA = StructType([
    StructField("patient_id",       StringType(),  False),
    StructField("protocol_key",     StringType(),  False),
    StructField("protocol_name",    StringType(),  False),
    StructField("action_key",       StringType(),  False),
    StructField("action_label",     StringType(),  False),
    StructField("action_severity",  StringType(),  False),
    StructField("urgency",          StringType(),  False),
    StructField("owner",            StringType(),  False),
    StructField("citation",         StringType(),  False),
    StructField("trigger_pattern",  StringType(),  False),
    StructField("trigger_evidence", StringType(),  False),
    StructField("trigger_start",    IntegerType(), False),
    StructField("trigger_end",      IntegerType(), False),
]) if DataFrame is not None else None


def transform(notes: "DataFrame") -> "DataFrame":
    """Pipeline Builder calls this. Input: notes(patient_id, note_text)."""
    spark = SparkSession.builder.getOrCreate()

    def _flatten(rows: Iterator[Any]) -> Iterator[Dict[str, Any]]:
        for r in rows:
            for gap in detect_gaps_for_note(r["patient_id"], r["note_text"] or ""):
                yield gap

    rdd = notes.select("patient_id", "note_text").rdd.mapPartitions(_flatten)
    return spark.createDataFrame(rdd, schema=OUTPUT_SCHEMA)


# ---------------------------------------------------------------------------
# Local smoke test — run `python pipeline_protocol_gap_transform.py` to verify
# parity with the backend before pasting into Pipeline Builder.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys, pathlib
    notes_json = pathlib.Path(__file__).resolve().parents[1] / "backend" / "app" / "data" / "patient_notes.json"
    if not notes_json.exists():
        print("notes file not found; smoke test skipped", file=sys.stderr)
        sys.exit(0)

    corpus = json.loads(notes_json.read_text())
    total = 0
    by_proto: Dict[str, int] = {}
    by_patient: Dict[str, int] = {}
    for n in corpus:
        gaps = detect_gaps_for_note(n["patient_id"], n["note_text"])
        total += len(gaps)
        by_patient[n["patient_id"]] = len(gaps)
        for g in gaps:
            by_proto[g["protocol_key"]] = by_proto.get(g["protocol_key"], 0) + 1

    print(f"corpus: {len(corpus)} notes")
    print(f"total gaps: {total}")
    print(f"by protocol: {by_proto}")
    patients_with_gaps = sum(1 for v in by_patient.values() if v > 0)
    print(f"patients with >=1 gap: {patients_with_gaps}")
