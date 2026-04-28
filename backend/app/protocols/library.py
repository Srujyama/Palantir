"""
Care-pathway protocol library.

Each protocol encodes a published standard-of-care bundle as structured rules:

  - `triggers`: phrase / lab / vital patterns that mean "this protocol applies"
  - `expected_actions`: phrase patterns that mean "this required step IS documented"
  - `time_window_hours`: window within which the bundle should be initiated
  - `owner`: who acts when something is missing
  - `urgency`: red / amber / green if the bundle is incomplete

Sources (publicly cited bundles): Surviving Sepsis Campaign hour-1 bundle,
ACC/AHA NSTEMI guidelines, AHA/ASA acute ischemic stroke window, ADA DKA
management, IDSA CAP guidelines.

This is intentionally rules-based, not a black box. In a real Foundry
deployment the same library would live as an ontology object set with
versioning and clinician sign-off.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class Protocol:
    key: str
    name: str
    triggers: List[str]                  # any-of: regex/phrase patterns in note text
    expected_actions: List["ExpectedAction"]
    time_window_hours: int
    owner: str
    urgency_if_incomplete: str           # red | amber | green
    citation: str


@dataclass(frozen=True)
class ExpectedAction:
    key: str
    label: str                           # human-readable action
    documented_patterns: List[str]       # any-of: if matched, action IS documented
    severity: str = "required"           # required | recommended


SEPSIS = Protocol(
    key="sepsis",
    name="Surviving Sepsis Hour-1 Bundle",
    triggers=[
        r"\bsepsis\b", r"\bseptic\b", r"\bSIRS\b",
        r"lactate\s*[>:]?\s*[2-9]",      # lactate > 2
        r"hypotension", r"\bMAP\b\s*<", r"BP\s*\d{2}/\d{2}",
    ],
    expected_actions=[
        ExpectedAction(
            "lactate",
            "Measure serum lactate",
            [r"\blactate\b\s*\d", r"lactate\s+drawn", r"lactate\s+result"],
        ),
        ExpectedAction(
            "blood_cx",
            "Draw blood cultures before antibiotics",
            [r"blood\s+culture", r"\bBCx\b"],
        ),
        ExpectedAction(
            "antibiotics",
            "Administer broad-spectrum antibiotics",
            [
                r"\b(antibiotic|antibiotics|abx)\b\s*(given|started|administered|initiated|ordered)",
                r"\b(vancomycin|piperacillin|tazobactam|cefepime|meropenem|ceftriaxone|zosyn|cefazolin|levofloxacin|azithromycin|ciprofloxacin)\b",
            ],
        ),
        ExpectedAction(
            "fluids",
            "Begin 30 mL/kg crystalloid resuscitation",
            [r"30\s*mL/kg", r"fluid\s+bolus", r"IV\s+fluids?\s+(initiated|bolus|running)"],
        ),
    ],
    time_window_hours=1,
    owner="physician",
    urgency_if_incomplete="red",
    citation="Surviving Sepsis Campaign Hour-1 Bundle (2018)",
)


ACS = Protocol(
    key="acs",
    name="NSTEMI / Unstable Angina Initial Management",
    triggers=[
        r"\bNSTEMI\b", r"\bSTEMI\b", r"\bACS\b",
        r"chest\s+(pain|pressure|tightness)\b.*(troponin|ECG|EKG)",
        r"troponin\s+(I\s+)?(elevated|positive|\d+\.\d+)",
        r"ST\s*(depression|elevation)",
    ],
    expected_actions=[
        ExpectedAction(
            "asa",
            "Aspirin 162-325 mg given",
            [r"\bASA\b\s*(\d+\s*(mg)?)?\s*(given|administered|chewed)", r"aspirin\s+\d"],
        ),
        ExpectedAction(
            "anticoag",
            "Anticoagulation (heparin or LMWH)",
            [r"\b(heparin|enoxaparin|lovenox|fondaparinux)\b"],
        ),
        ExpectedAction(
            "cards_consult",
            "Cardiology consult",
            [r"cardiology\s+(consult|notified|aware|to\s+see)"],
        ),
        ExpectedAction(
            "serial_trop",
            "Serial troponin / ECG monitoring",
            [r"repeat\s+(troponin|ECG|EKG)", r"serial\s+(troponin|ECG)", r"telemetry"],
        ),
    ],
    time_window_hours=2,
    owner="physician",
    urgency_if_incomplete="red",
    citation="ACC/AHA NSTEMI Guidelines",
)


STROKE = Protocol(
    key="stroke",
    name="Acute Ischemic Stroke / tPA Window",
    triggers=[
        r"\bstroke\b", r"\bCVA\b", r"hemiparesis", r"hemiplegia",
        r"\bNIHSS\b", r"aphasi[ac]", r"facial\s+droop", r"last\s+known\s+well",
    ],
    expected_actions=[
        ExpectedAction(
            "ct_head",
            "Non-contrast head CT",
            [r"head\s+CT", r"CT\s+head", r"non-?contrast\s+CT"],
        ),
        ExpectedAction(
            "neuro_consult",
            "Neurology consult / stroke team activation",
            [
                r"neurology\s+(consult|notified|aware|to\s+see)",
                r"stroke\s+(team|alert|code)\s+(activated|called|notified)",
            ],
        ),
        ExpectedAction(
            "tpa_eval",
            "tPA / thrombolytic eligibility evaluation",
            [r"\btPA\b", r"alteplase", r"thrombolytic", r"thrombectomy"],
        ),
        ExpectedAction(
            "bp_control",
            "Blood pressure control",
            [r"BP\s+control", r"nicardipine", r"labetalol", r"antihypertensive"],
        ),
    ],
    time_window_hours=1,
    owner="physician",
    urgency_if_incomplete="red",
    citation="AHA/ASA Acute Ischemic Stroke Guidelines",
)


CAP = Protocol(
    key="cap",
    name="Community-Acquired Pneumonia Initial Management",
    triggers=[
        r"community-?acquired\s+pneumonia", r"\bCAP\b\b",
        r"pneumonia.*CURB",
        r"\bpneumonia\b.*(consolidation|infiltrate)",
    ],
    expected_actions=[
        ExpectedAction(
            "antibiotics",
            "Empiric antibiotics within 6h of arrival",
            [
                r"\b(ceftriaxone|azithromycin|levofloxacin|moxifloxacin|doxycycline|amoxicillin)\b",
                r"\bantibiotics?\s+(given|started|administered)",
            ],
        ),
        ExpectedAction(
            "blood_cx",
            "Blood cultures if severe",
            [r"blood\s+culture", r"\bBCx\b"],
        ),
        ExpectedAction(
            "o2_assessment",
            "Oxygenation assessed (SpO2 or ABG)",
            [r"SpO2", r"\bABG\b", r"oxygen\s+saturation"],
        ),
    ],
    time_window_hours=6,
    owner="physician",
    urgency_if_incomplete="amber",
    citation="IDSA/ATS Community-Acquired Pneumonia Guidelines",
)


DKA = Protocol(
    key="dka",
    name="Diabetic Ketoacidosis Management",
    triggers=[
        r"\bDKA\b", r"diabetic\s+ketoacidosis",
        r"anion\s+gap\s+\d{2}", r"beta-?hydroxybutyrate",
        r"glucose\s*[>:]?\s*[3-9]\d{2}",
    ],
    expected_actions=[
        ExpectedAction(
            "insulin",
            "Insulin infusion initiated",
            [r"insulin\s+(drip|infusion|bolus|started)", r"\b0\.1\s*units?/kg"],
        ),
        ExpectedAction(
            "fluids",
            "IV fluid resuscitation",
            [r"IV\s+fluids?", r"normal\s+saline", r"\bNS\b\s+(bolus|running)"],
        ),
        ExpectedAction(
            "k_replace",
            "Potassium repletion if K < 5.3",
            [r"potassium\s+(repletion|replacement|added)", r"\bKCl\b", r"K\s+\d"],
        ),
        ExpectedAction(
            "monitor_gap",
            "Serial anion gap / electrolytes",
            [r"repeat\s+(labs|BMP|chem|gap)", r"serial\s+(labs|gap|electrolytes)"],
        ),
    ],
    time_window_hours=2,
    owner="physician",
    urgency_if_incomplete="red",
    citation="ADA DKA Management Guidelines",
)


PROTOCOLS: List[Protocol] = [SEPSIS, ACS, STROKE, CAP, DKA]


def by_key(key: str) -> Protocol | None:
    for p in PROTOCOLS:
        if p.key == key:
            return p
    return None
