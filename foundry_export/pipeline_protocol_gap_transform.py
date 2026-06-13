"""
Pipeline Builder — Python transform: protocol-gap detection.

GENERATED FROM backend/app/protocols/library.py and
backend/app/services/silent_failure.py — do not edit by hand; regenerate
with:  python sync_transform.py
Parity with the local engine is enforced by
backend/tests/test_foundry_parity.py over the full 176-note corpus.

Self-contained. Paste this whole file into a Pipeline Builder Python
transform node. The protocol library and the context/negation rules are
inlined so there are no imports beyond pyspark and the standard library.

Inputs (two Foundry datasets, joined by patient_id):
  - notes:       columns [patient_id (string), note_text (string)]
  - protocols:   not used at runtime — kept in source control for traceability
                 and for re-derivation if rules change. The rules below are
                 the source of truth for this transform.

Output dataset:
  protocol_gaps — one row per (patient, triggered protocol, missing step)

Output schema:
  patient_id              string
  protocol_key            string   sepsis | acs | stroke | cap | dka | pe |
                                   gi_bleed | aki | ciwa | neutropenic_fever |
                                   hyperkalemia | copd
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

Context semantics (lifted verbatim from silent_failure.py):
  * negation cues ("denies", "no ", "ruled out"...) suppress a trigger only
    from the LEFT, clipped to the trigger's own sentence;
  * historical/resolution cues ("history of", "days ago", "resolved"...)
    suppress from either side, same-sentence only;
  * ambiguous triggers (e.g. "CVA", mild-AKI language) require corroborating
    context elsewhere in the note before firing;
  * per-protocol resolution phrases ("anion gap closed", "two negative
    troponins"...) retire the whole bundle for that note.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional

# Pipeline Builder injects pyspark — import lazily so this file is also
# runnable as a unit test outside Foundry.
try:
    from pyspark.sql import DataFrame, SparkSession
    from pyspark.sql.types import (
        IntegerType, StringType, StructField, StructType,
    )
except Exception:  # pragma: no cover — only happens when running locally
    DataFrame = SparkSession = None  # type: ignore


# ---------------------------------------------------------------------------
# Protocol library — generated from backend/app/protocols/library.py.
# The list IS the rule engine.
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
            r"\bsepsis\b",
            r"\bseptic\b",
            r"\bSIRS\b",
            r"lactate\s*[>:]?\s*(?:[4-9]|[1-9]\d)(?:\.\d)?",
            "hypotension",
            r"\bMAP\b\s*<",
            r"BP\s*\d{2}/\d{2}",
        ],
        "actions": [
            {
                "key": "lactate",
                "severity": "required",
                "label": "Measure serum lactate",
                "documented": [
                    r"\blactate\b\s*\d",
                    r"lactate\s+drawn",
                    r"lactate\s+result",
                ],
            },
            {
                "key": "blood_cx",
                "severity": "required",
                "label": "Draw blood cultures before antibiotics",
                "documented": [
                    r"blood\s+culture",
                    r"\bBCx\b",
                ],
            },
            {
                "key": "antibiotics",
                "severity": "required",
                "label": "Administer broad-spectrum antibiotics",
                "documented": [
                    r"\b(antibiotic|antibiotics|abx)\b\s*(given|started|administered|initiated|ordered)",
                    r"broad-?spectrum\s+(antibiotics?|abx)",
                    r"\b(vancomycin|piperacillin|tazobactam|cefepime|meropenem|ceftriaxone|zosyn|cefazolin|levofloxacin|azithromycin|ciprofloxacin)\b",
                ],
            },
            {
                "key": "fluids",
                "severity": "required",
                "label": "Begin 30 mL/kg crystalloid resuscitation",
                "documented": [
                    r"30\s*mL/kg",
                    r"fluid\s+bolus",
                    r"IV\s+fluids?\s+(initiated|bolus|running)",
                    r"\bIVF\b",
                ],
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
            r"\bNSTEMI\b",
            r"\bSTEMI\b",
            r"\bACS\b",
            r"chest\s+(pain|pressure|tightness)\b.*(troponin|ECG|EKG)",
            r"troponin\s+(I\s+)?(elevated|positive|\d+\.\d+)",
            r"ST\s*(depression|elevation)",
        ],
        "actions": [
            {
                "key": "asa",
                "severity": "required",
                "label": "Aspirin 162-325 mg given",
                "documented": [
                    r"\bASA\b\s*(\d+\s*(mg)?)?\s*(given|administered|chewed)",
                    r"aspirin\s+\d",
                ],
            },
            {
                "key": "anticoag",
                "severity": "required",
                "label": "Anticoagulation (heparin or LMWH)",
                "documented": [
                    r"\b(heparin|enoxaparin|lovenox|fondaparinux)\b",
                ],
            },
            {
                "key": "cards_consult",
                "severity": "required",
                "label": "Cardiology consult",
                "documented": [
                    r"cardiology\s+(consult|notified|aware|to\s+see)",
                ],
            },
            {
                "key": "serial_trop",
                "severity": "required",
                "label": "Serial troponin / ECG monitoring",
                "documented": [
                    r"repeat\s+(troponin|ECG|EKG)",
                    r"serial\s+(troponin|ECG)",
                    "telemetry",
                ],
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
            r"\bstroke\b",
            r"\bCVA\b",
            "hemiparesis",
            "hemiplegia",
            r"\bNIHSS\b",
            "aphasi[ac]",
            r"facial\s+droop",
            r"last\s+known\s+well",
        ],
        "actions": [
            {
                "key": "ct_head",
                "severity": "required",
                "label": "Non-contrast head CT",
                "documented": [
                    r"head\s+CT",
                    r"CT\s+head",
                    r"non-?contrast\s+CT",
                ],
            },
            {
                "key": "neuro_consult",
                "severity": "required",
                "label": "Neurology consult / stroke team activation",
                "documented": [
                    r"neurology\s+(consult|notified|aware|to\s+see)",
                    r"stroke\s+(team|alert|code)\s+(activated|called|notified)",
                ],
            },
            {
                "key": "tpa_eval",
                "severity": "required",
                "label": "tPA / thrombolytic eligibility evaluation",
                "documented": [
                    r"\btPA\b",
                    "alteplase",
                    "thrombolytic",
                    "thrombectomy",
                ],
            },
            {
                "key": "bp_control",
                "severity": "required",
                "label": "Blood pressure control",
                "documented": [
                    r"BP\s+control",
                    "nicardipine",
                    "labetalol",
                    "antihypertensive",
                ],
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
            r"community-?acquired\s+pneumonia",
            r"\bCAP\b",
            "pneumonia.*CURB",
            r"\bpneumonia\b.*(consolidation|infiltrate)",
        ],
        "actions": [
            {
                "key": "antibiotics",
                "severity": "required",
                "label": "Empiric antibiotics within 6h of arrival",
                "documented": [
                    r"\b(ceftriaxone|azithromycin|levofloxacin|moxifloxacin|doxycycline|amoxicillin)\b",
                    r"\bantibiotics?\s+(given|started|administered)",
                ],
            },
            {
                "key": "blood_cx",
                "severity": "required",
                "label": "Blood cultures if severe",
                "documented": [
                    r"blood\s+culture",
                    r"\bBCx\b",
                ],
            },
            {
                "key": "o2_assessment",
                "severity": "required",
                "label": "Oxygenation assessed (SpO2 or ABG)",
                "documented": [
                    "SpO2",
                    r"\bABG\b",
                    r"oxygen\s+saturation",
                ],
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
            r"\bDKA\b",
            r"diabetic\s+ketoacidosis",
            r"anion\s+gap\s+\d{2}",
            "beta-?hydroxybutyrate",
            r"glucose\s*[>:]?\s*[3-9]\d{2}",
        ],
        "actions": [
            {
                "key": "insulin",
                "severity": "required",
                "label": "Insulin infusion initiated",
                "documented": [
                    r"insulin\s+(drip|infusion|bolus|started)",
                    r"\b0\.1\s*units?/kg",
                ],
            },
            {
                "key": "fluids",
                "severity": "required",
                "label": "IV fluid resuscitation",
                "documented": [
                    r"IV\s+fluids?",
                    r"normal\s+saline",
                    r"\bNS\b\s+(bolus|running)",
                ],
            },
            {
                "key": "k_replace",
                "severity": "required",
                "label": "Potassium repletion if K < 5.3",
                "documented": [
                    r"potassium\s+(repletion|replacement|added|repleted|replaced)",
                    r"\bKCl\b",
                    r"replet\w*\s+K\b",
                    r"\bK\s+(rider|repletion|replacement|repleted|replaced)\b",
                ],
            },
            {
                "key": "monitor_gap",
                "severity": "required",
                "label": "Serial anion gap / electrolytes",
                "documented": [
                    r"repeat\s+(labs|BMP|chem|gap)",
                    r"serial\s+(labs|gap|electrolytes)",
                ],
            },
        ],
    },
    {
        "key": "pe",
        "name": "Pulmonary Embolism Initial Management",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 2,
        "citation": "ESC/AHA Pulmonary Embolism Guidelines",
        "triggers": [
            r"\bpulmonary\s+embol",
            r"(suspected|confirmed|diagnosed|acute)\s+PE\b",
            r"\bPE\b\s*(suspected|confirmed|diagnosed)",
            r"confirms?\s+(bilateral\s+)?(segmental\s+|subsegmental\s+)?PE\b",
            r"\bCTPA\s+(positive|confirms)",
            r"right\s+heart\s+strain",
            r"submassive\s+PE\b",
            r"massive\s+PE\b",
        ],
        "actions": [
            {
                "key": "anticoag",
                "severity": "required",
                "label": "Therapeutic anticoagulation initiated",
                "documented": [
                    r"\b(heparin|enoxaparin|lovenox|apixaban|rivaroxaban)\b",
                    r"therapeutic\s+anticoagulation",
                ],
            },
            {
                "key": "imaging",
                "severity": "required",
                "label": "Confirmatory CT-PA or VQ scan",
                "documented": [
                    "CT-?PA",
                    r"V/?Q\s+scan",
                    r"pulmonary\s+angiogram",
                ],
            },
            {
                "key": "risk_stratify",
                "severity": "required",
                "label": "Risk stratification (RV strain, troponin, BNP)",
                "documented": [
                    r"\btroponin\b",
                    r"\bBNP\b",
                    "echocardiogram",
                    r"RV\s+(strain|dysfunction|dilation)",
                ],
            },
            {
                "key": "monitor",
                "severity": "required",
                "label": "Telemetry / continuous monitoring",
                "documented": [
                    "telemetry",
                    r"continuous\s+monitoring",
                    r"\bICU\b",
                ],
            },
        ],
    },
    {
        "key": "gi_bleed",
        "name": "Upper GI Bleed Initial Management",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 2,
        "citation": "ACG Upper GI Bleed Guidelines",
        "triggers": [
            r"\bGIB\b",
            r"GI\s+bleed",
            "melena",
            "hematemesis",
            r"coffee-?ground\s+emesis",
            r"hemoglobin\s+drop",
            r"hgb\s+(dropped|decreased)\s+to",
        ],
        "actions": [
            {
                "key": "ivf_access",
                "severity": "required",
                "label": "Two large-bore IV access + IV fluids",
                "documented": [
                    r"\btwo\s+large-?bore\b",
                    r"large-?bore\s+IV",
                    r"IV\s+fluids?\s+(running|bolus|initiated)",
                ],
            },
            {
                "key": "type_screen",
                "severity": "required",
                "label": "Type and screen / type and cross",
                "documented": [
                    r"type\s+and\s+(screen|cross)",
                    r"\bT&S\b",
                    r"\bT&C\b",
                ],
            },
            {
                "key": "ppi",
                "severity": "required",
                "label": "IV proton-pump inhibitor",
                "documented": [
                    r"\b(pantoprazole|protonix|esomeprazole|nexium)\b",
                    r"\bPPI\b\s+(drip|infusion)",
                ],
            },
            {
                "key": "gi_consult",
                "severity": "required",
                "label": "GI consult / endoscopy plan",
                "documented": [
                    r"\bGI\s+(consult|notified|aware|to\s+see)",
                    r"\bendoscopy\b",
                    r"\bEGD\b",
                ],
            },
        ],
    },
    {
        "key": "aki",
        "name": "Acute Kidney Injury Workup",
        "owner": "physician",
        "urgency": "amber",
        "time_window_hours": 12,
        "citation": "KDIGO Acute Kidney Injury Guidelines",
        "triggers": [
            r"\bAKI\b",
            r"acute\s+kidney\s+injury",
            r"creatinine\s+(rising|rose|increased|elevated)",
            r"creatinine\s+(from\s+)?[01]\.\d\s+to\s+[2-9]",
            r"UOP\s*<",
            "oliguria",
            "anuria",
        ],
        "actions": [
            {
                "key": "med_review",
                "severity": "required",
                "label": "Medication review for nephrotoxins",
                "documented": [
                    r"h[eo]ld\w*\s+(NSAIDs?|ibuprofen|naproxen|ACE\w*|ARBs?|lisinopril|losartan|vancomycin|tobramycin|gentamicin|aminoglycosides?|contrast|nephrotoxi\w+)",
                    r"nephrotoxic\s+(review|hold|stop)",
                    r"pharmacy\s+review",
                    r"renal\s+dosing",
                ],
            },
            {
                "key": "volume_assessment",
                "severity": "required",
                "label": "Volume status assessment",
                "documented": [
                    r"\b(euvolemic|hypovolemic|hypervolemic)\b",
                    r"\bJVP\b",
                    "orthostatic",
                    r"fluid\s+(challenge|trial|bolus)",
                ],
            },
            {
                "key": "urine_studies",
                "severity": "required",
                "label": "Urine studies (FENa, sediment, electrolytes)",
                "documented": [
                    r"\bFENa\b",
                    r"urine\s+(sediment|electrolytes|sodium)",
                    r"muddy\s+brown",
                ],
            },
            {
                "key": "renal_us",
                "severity": "required",
                "label": "Renal ultrasound to evaluate obstruction",
                "documented": [
                    r"renal\s+(US|ultrasound)",
                    r"\bhydronephrosis\b",
                ],
            },
        ],
    },
    {
        "key": "ciwa",
        "name": "Alcohol Withdrawal (CIWA-Ar Protocol)",
        "owner": "physician",
        "urgency": "amber",
        "time_window_hours": 2,
        "citation": "ASAM Alcohol Withdrawal Management Guidelines",
        "triggers": [
            r"alcohol\s+(withdrawal|use\s+disorder)",
            r"\bCIWA\b",
            r"last\s+drink\s+\d",
            r"history\s+of\s+(DTs|delirium\s+tremens|withdrawal\s+seizures?)",
            r"\bAUD\b",
        ],
        "actions": [
            {
                "key": "ciwa_scoring",
                "severity": "required",
                "label": "CIWA-Ar scoring documented q1-2h",
                "documented": [
                    r"CIWA(-Ar)?\s+(score|scoring|q\d)",
                    r"withdrawal\s+scoring",
                ],
            },
            {
                "key": "benzo",
                "severity": "required",
                "label": "Benzodiazepine protocol (symptom-triggered)",
                "documented": [
                    r"\b(lorazepam|ativan|diazepam|valium|chlordiazepoxide|librium)\b",
                    r"benzodiazepine\s+(taper|protocol|drip)",
                    "symptom-?triggered",
                ],
            },
            {
                "key": "thiamine",
                "severity": "required",
                "label": "Thiamine + multivitamin (banana bag)",
                "documented": [
                    r"\bthiamine\b",
                    r"banana\s+bag",
                    r"\bIV\s+B-?complex\b",
                ],
            },
            {
                "key": "seizure_precautions",
                "severity": "required",
                "label": "Seizure precautions and monitoring",
                "documented": [
                    r"seizure\s+(precautions|monitoring|watch)",
                    r"padded\s+rails",
                ],
            },
        ],
    },
    {
        "key": "neutropenic_fever",
        "name": "Neutropenic Fever Empiric Management",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 1,
        "citation": "IDSA Febrile Neutropenia Guidelines",
        "triggers": [
            r"neutropenic\s+fever",
            r"\bANC\s*[<:]?\s*\d{1,3}\b",
            r"ANC\s+(of\s+)?\d{1,3}\b",
            r"febrile\s+neutropenia",
            "chemo(therapy)?.{0,40}fever",
            "fever.{0,40}(chemo|induction|neutropenic)",
        ],
        "actions": [
            {
                "key": "antibiotics",
                "severity": "required",
                "label": "Empiric broad-spectrum antibiotics within 60 min",
                "documented": [
                    r"\b(cefepime|piperacillin|tazobactam|zosyn|meropenem|imipenem)\b",
                    r"empiric\s+(antibiotics?|abx)",
                ],
            },
            {
                "key": "blood_cx",
                "severity": "required",
                "label": "Blood cultures x2 (including from line)",
                "documented": [
                    r"blood\s+cultures?\s+x\s*2",
                    r"cultures\s+from\s+(line|port|central)",
                ],
            },
            {
                "key": "isolation",
                "severity": "required",
                "label": "Neutropenic precautions / isolation",
                "documented": [
                    r"neutropenic\s+(precautions|isolation)",
                    r"reverse\s+isolation",
                ],
            },
            {
                "key": "oncology_notified",
                "severity": "required",
                "label": "Oncology team notified",
                "documented": [
                    r"oncology\s+(notified|consult|aware|to\s+see)",
                    r"primary\s+oncologist",
                ],
            },
        ],
    },
    {
        "key": "hyperkalemia",
        "name": "Severe Hyperkalemia Treatment",
        "owner": "physician",
        "urgency": "red",
        "time_window_hours": 1,
        "citation": "ESC/AHA Hyperkalemia Management Consensus",
        "triggers": [
            r"\bK\s*[: ]?\s*([6-9]\.\d|\d{2}\.\d)",
            "hyperkalemia",
            r"potassium\s+(elevated|high|of)\s+\d",
            r"peaked\s+T-?waves?",
        ],
        "actions": [
            {
                "key": "ecg",
                "severity": "required",
                "label": "ECG to assess for hyperkalemic changes",
                "documented": [
                    r"\b(ECG|EKG)\b",
                    r"peaked\s+T",
                    r"\bQRS\s+widening\b",
                ],
            },
            {
                "key": "stabilize_membrane",
                "severity": "required",
                "label": "Calcium gluconate / chloride for membrane stabilization",
                "documented": [
                    r"calcium\s+(gluconate|chloride)",
                    r"\bIV\s+calcium\b",
                ],
            },
            {
                "key": "shift_intracellular",
                "severity": "required",
                "label": "Insulin + dextrose to shift potassium intracellularly",
                "documented": [
                    r"insulin\s+(and|\+)\s+(D50|dextrose|glucose)",
                    "D50.*insulin",
                    r"\bbeta-?agonist\b",
                    r"albuterol\s+nebulizer",
                ],
            },
            {
                "key": "remove",
                "severity": "required",
                "label": "Removal: diuretic, kayexalate, or dialysis",
                "documented": [
                    r"\b(furosemide|lasix|patiromer|kayexalate|sodium\s+polystyrene)\b",
                    r"\bdialysis\b",
                    r"\bCRRT\b",
                    r"\bHD\b(?!\s*#?\s*\d)",
                ],
            },
        ],
    },
    {
        "key": "copd",
        "name": "COPD Exacerbation Management",
        "owner": "physician",
        "urgency": "amber",
        "time_window_hours": 4,
        "citation": "GOLD COPD Strategy",
        "triggers": [
            r"COPD\s+exacerbation",
            r"acute\s+exacerbation\s+of\s+COPD",
            r"\bAECOPD\b",
            r"increased\s+(sputum|dyspnea).*COPD",
        ],
        "actions": [
            {
                "key": "bronchodilator",
                "severity": "required",
                "label": "Short-acting bronchodilators (DuoNeb / albuterol-ipratropium)",
                "documented": [
                    r"\b(albuterol|ipratropium|duoneb|combivent|nebulizer)\b",
                    "bronchodilator",
                ],
            },
            {
                "key": "steroids",
                "severity": "required",
                "label": "Systemic corticosteroids",
                "documented": [
                    r"\b(prednisone|methylprednisolone|solu-?medrol|dexamethasone)\b",
                    r"systemic\s+steroids",
                ],
            },
            {
                "key": "antibiotics",
                "severity": "required",
                "label": "Antibiotics if sputum purulence increased",
                "documented": [
                    r"\b(azithromycin|doxycycline|amoxicillin|levofloxacin)\b",
                    r"antibiotic\s+for\s+exacerbation",
                ],
            },
            {
                "key": "oxygen_target",
                "severity": "required",
                "label": "Controlled oxygen targeted SpO2 88-92%",
                "documented": [
                    r"SpO2\s+(target|goal)\s+88",
                    r"controlled\s+oxygen",
                    r"titrate\s+(O2|oxygen)",
                ],
            },
        ],
    },
]

# ---------------------------------------------------------------------------
# Context / negation rules — generated from backend/app/services/silent_failure.py
# ---------------------------------------------------------------------------

_NEGATION_TOKENS_LEFT = [
    "denies",
    "no ",
    "not ",
    "ruled out",
    "negative",
    "without",
    "free of",
]
_HISTORICAL_TOKENS = [
    "resolved",
    "improving",
    "improved",
    "history of",
    "h/o",
    "prior",
    "previous",
    "stable",
    "afebrile",
    "admitted",
    "days ago",
    "weeks ago",
    "last admission",
    "post-op",
    "post op",
    "second admission",
    "third admission",
]
_NEGATION_WINDOW = 60
_SENTENCE_BOUNDARY = re.compile(r"[.!?;\n]")

_PROTOCOL_RESOLUTION_PHRASES: Dict[str, List[str]] = {
    "dka": [
        r"DKA\s+resolved",
        r"anion\s+gap\s+closed",
        r"gap\s+closed",
        r"bicarbonate\s+(2[0-9]|[3-9]\d)",
    ],
    "sepsis": [
        r"sepsis\s+resolved",
        r"afebrile\s+for",
    ],
    "stroke": [
        r"stroke\s+resolved",
        r"deficits\s+resolved",
        r"(stroke|tPA|thrombolysis)\s+window\s+(expired|closed|passed)",
    ],
    "cap": [
        r"pneumonia\s+(resolved|improving)",
    ],
    "acs": [
        r"chest\s+pain\s+resolved",
        r"troponin\s+down-?trending",
        r"two\s+negative\s+troponins?",
        r"troponins?\s+x\s*2\s+negative",
        r"chest\s+pain.{0,40}ruled\s+out",
        r"non-?cardiac\s+chest\s+pain",
    ],
    "pe": [
        r"PE\s+resolved",
        r"clot\s+burden\s+(decreased|improving)",
    ],
    "gi_bleed": [
        r"bleeding\s+(stopped|resolved)",
        r"hgb\s+(stable|recovered)",
    ],
    "aki": [
        r"AKI\s+(resolved|improving)",
        r"creatinine\s+(returned|back\s+to\s+baseline)",
        r"renal\s+function\s+recovered",
    ],
    "ciwa": [
        r"CIWA\s+(score|scores)\s+(<\s*8|low|0)",
        r"withdrawal\s+resolved",
    ],
    "neutropenic_fever": [
        r"ANC\s+(recovered|>\s*500)",
        r"afebrile\s+for\s+\d+",
    ],
    "hyperkalemia": [
        r"potassium\s+(normalized|corrected|back\s+to)",
        r"K\s+(3\.\d|4\.\d|5\.[0-2])",
    ],
    "copd": [
        r"COPD\s+exacerbation,?\s+resolved",
        r"COPD\s+stable",
        r"back\s+to\s+baseline",
    ],
}

_AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT: Dict[str, List[str]] = {
    r"\bCVA\b": [
        "stroke",
        "infarct",
        "tPA",
        "NIHSS",
        "hemiparesis",
        "aphasi",
        "facial droop",
    ],
    r"\bAKI\b": [
        r"(?:creatinine|\bCr\b)\s*[: ]?\s*(?:[2-9]|[1-9]\d)\.\d",
        r"\bto\s+(?:[2-9]|[1-9]\d)\.\d",
        r"\bUOP\s*<",
        "oliguri",
        "anuri",
        r"muddy\s+brown",
    ],
    r"acute\s+kidney\s+injury": [
        r"(?:creatinine|\bCr\b)\s*[: ]?\s*(?:[2-9]|[1-9]\d)\.\d",
        r"\bto\s+(?:[2-9]|[1-9]\d)\.\d",
        r"\bUOP\s*<",
        "oliguri",
        "anuri",
        r"muddy\s+brown",
    ],
    r"creatinine\s+(rising|rose|increased|elevated)": [
        r"(?:creatinine|\bCr\b)\s*[: ]?\s*(?:[2-9]|[1-9]\d)\.\d",
        r"\bto\s+(?:[2-9]|[1-9]\d)\.\d",
        r"\bUOP\s*<",
        "oliguri",
        "anuri",
        r"muddy\s+brown",
    ],
}

# ---------------------------------------------------------------------------
# Pure-Python core (no Spark dependency) — the functions below are lifted
# verbatim from silent_failure.py by sync_transform.py.
# ---------------------------------------------------------------------------

@dataclass
class Span:
    start: int
    end: int
    text: str


def _is_negated_or_historical(note: str, span: Span) -> bool:
    left = note[max(0, span.start - _NEGATION_WINDOW): span.start].lower()
    left = _SENTENCE_BOUNDARY.split(left)[-1]    # same sentence only
    right = note[span.end: span.end + _NEGATION_WINDOW].lower()
    right = _SENTENCE_BOUNDARY.split(right)[0]   # same sentence only
    # Negation precedes its concept in English clinical prose: left only.
    if any(tok in left for tok in _NEGATION_TOKENS_LEFT):
        return True
    # Historical/resolution context can sit on either side of the trigger.
    return any(tok in left or tok in right for tok in _HISTORICAL_TOKENS)

def _ambiguous_trigger_passes(note: str, pattern: str, span: Span) -> bool:
    needs = _AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT.get(pattern)
    if not needs:
        return True
    return any(re.search(kw, note, flags=re.IGNORECASE) for kw in needs)

def _find_first(note: str, patterns: List[str]) -> Span | None:
    """Find the first trigger that is neither historical/negated nor an
    ambiguous abbreviation lacking corroborating context."""
    for pat in patterns:
        for m in re.finditer(pat, note, flags=re.IGNORECASE):
            span = Span(m.start(), m.end(), m.group(0))
            if _is_negated_or_historical(note, span):
                continue
            if not _ambiguous_trigger_passes(note, pat, span):
                continue
            return span
    return None

def _any_match(note: str, patterns: List[str]) -> bool:
    return any(re.search(p, note, flags=re.IGNORECASE) for p in patterns)

def _protocol_resolved(note: str, proto_key: str) -> bool:
    for pat in _PROTOCOL_RESOLUTION_PHRASES.get(proto_key, []):
        if re.search(pat, note, flags=re.IGNORECASE):
            return True
    return False

def detect_gaps_for_note(patient_id: str, note: str) -> List[Dict[str, Any]]:
    """Return one dict per (triggered protocol, missing step) for this note.

    Mirrors silent_failure.evaluate(): iterating patterns one at a time
    through _find_first gives the identical first surviving trigger while
    retaining which pattern produced it (for the trigger_pattern column).
    """
    rows: List[Dict[str, Any]] = []
    if not note:
        return rows

    for proto in PROTOCOLS:
        trig: Optional[Span] = None
        trig_pattern: Optional[str] = None
        for pat in proto["triggers"]:
            span = _find_first(note, [pat])
            if span is not None:
                trig, trig_pattern = span, pat
                break
        if trig is None or _protocol_resolved(note, proto["key"]):
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
                "trigger_pattern":  trig_pattern,
                "trigger_evidence": trig.text,
                "trigger_start":    trig.start,
                "trigger_end":      trig.end,
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
