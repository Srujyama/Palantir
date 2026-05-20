"""
Clinical NLP extractor.

Extracts structured signals from a free-text patient note:

  * Vitals (BP, HR, RR, SpO2, Temp)
  * Labs (WBC, lactate, troponin, creatinine, glucose, hemoglobin, INR, K, Na)
  * Medications (named drug list, with light class tagging)
  * Operational signals (consults requested, imaging ordered, dispo blockers)
  * Standard-of-care signals (presence/absence of expected protocol actions)

Each finding carries:
  - the exact span and offsets in the source note (for evidence highlighting)
  - a label and a normalized value where applicable

The extractor is intentionally rules-based and inspectable. Real clinical NLP
production systems (cTAKES, MedSpaCy) layer ML on top of similar rule cores;
the rule core is what gives clinicians a story they can audit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Pattern, Tuple


@dataclass
class Span:
    start: int
    end: int
    text: str


@dataclass
class Finding:
    kind: str                  # vital | lab | med | consult | imaging | dispo | symptom | risk_factor
    label: str                 # human-readable name (e.g. "BP", "troponin", "vancomycin")
    value: Optional[str]       # normalized value (e.g. "88/52", "0.42", None for free text)
    evidence: Span
    metadata: Dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

VITAL_PATTERNS: List[Tuple[str, Pattern]] = [
    ("BP", re.compile(r"\bBP\s*[: ]?\s*(\d{2,3}\s*/\s*\d{2,3})", re.I)),
    ("HR", re.compile(r"\bHR\s*[: ]?\s*(\d{2,3})\b", re.I)),
    ("RR", re.compile(r"\bRR\s*[: ]?\s*(\d{1,2})\b", re.I)),
    ("SpO2", re.compile(r"SpO2\s*[: ]?\s*(\d{2,3}%?)", re.I)),
    ("Temp", re.compile(r"\b(?:fever|temp|temperature)\s+(?:to\s+)?(\d{2,3}(?:\.\d)?)\s*C?", re.I)),
]

LAB_PATTERNS: List[Tuple[str, Pattern]] = [
    ("WBC", re.compile(r"\bWBC\s*[: ]?\s*(\d{1,3}(?:\.\d)?)", re.I)),
    ("lactate", re.compile(r"\blactate\s*[: ]?\s*(\d{1,2}(?:\.\d)?)", re.I)),
    ("troponin", re.compile(r"\btroponin\s*(?:I|T)?\s*[: ]?\s*(\d+\.\d+)", re.I)),
    ("creatinine", re.compile(r"(?:creatinine|\bCr)\s*[: ]?\s*(\d{1,2}\.\d)", re.I)),
    ("glucose", re.compile(r"\bglucose\s*[: ]?\s*(\d{2,4})", re.I)),
    ("hemoglobin", re.compile(r"\b(?:hgb|hemoglobin|hb)\s*[: ]?\s*(\d{1,2}(?:\.\d)?)", re.I)),
    ("INR", re.compile(r"\bINR\s*[: ]?\s*(\d{1,2}\.\d)", re.I)),
    ("potassium", re.compile(r"\bK\s*[: ]?\s*(\d\.\d)", re.I)),
    ("sodium", re.compile(r"\b(?:Na|sodium)\s*[: ]?\s*(\d{2,3})\b", re.I)),
    ("BNP", re.compile(r"\bBNP\s*[: ]?\s*(\d{2,5})", re.I)),
    ("QTc", re.compile(r"\bQTc\s*[: ]?\s*(\d{3})\s*ms", re.I)),
    ("anion_gap", re.compile(r"\b(?:anion\s+)?gap\s*[: ]?\s*(\d{1,2})\b", re.I)),
    ("magnesium", re.compile(r"\bMg\s*[: ]?\s*(\d\.\d)", re.I)),
    ("ANC", re.compile(r"\bANC\s*(?:of)?\s*[: ]?\s*(\d{1,4})", re.I)),
    ("ph", re.compile(r"\bpH\s*[: ]?\s*(\d\.\d{1,2})", re.I)),
    ("bicarbonate", re.compile(r"\b(?:bicarb(?:onate)?|HCO3)\s*[: ]?\s*(\d{1,2})", re.I)),
    ("procalcitonin", re.compile(r"\bprocalcitonin\s*[: ]?\s*(\d+(?:\.\d+)?)", re.I)),
    ("d_dimer", re.compile(r"\bD-?dimer\s*[: ]?\s*(\d+(?:\.\d+)?)", re.I)),
]

# Medication name list (lowercase). Class tag drives downstream interaction
# checks. Not exhaustive — focused on the dataset's drug surface.
MEDICATIONS: Dict[str, str] = {
    # Antibiotics
    "vancomycin": "antibiotic",
    "tobramycin": "antibiotic_aminoglycoside_nephrotox",
    "ceftriaxone": "antibiotic",
    "azithromycin": "antibiotic_qt_prolong",
    "levofloxacin": "antibiotic_qt_prolong",
    "moxifloxacin": "antibiotic_qt_prolong",
    "piperacillin": "antibiotic",
    "tazobactam": "antibiotic",
    "zosyn": "antibiotic",
    "cefepime": "antibiotic",
    "meropenem": "antibiotic",
    "doxycycline": "antibiotic",
    "amoxicillin": "antibiotic",
    "nitrofurantoin": "antibiotic",
    "ciprofloxacin": "antibiotic_qt_prolong",
    # Cardiac
    "amiodarone": "antiarrhythmic_qt_prolong",
    "metoprolol": "beta_blocker",
    "carvedilol": "beta_blocker",
    "lisinopril": "ace_inhibitor",
    "losartan": "arb",
    "furosemide": "loop_diuretic",
    "spironolactone": "k_sparing_diuretic",
    # Antiplatelet / anticoag
    "aspirin": "antiplatelet",
    "clopidogrel": "antiplatelet",
    "apixaban": "anticoagulant_doac",
    "rivaroxaban": "anticoagulant_doac",
    "warfarin": "anticoagulant_vka",
    "heparin": "anticoagulant",
    "enoxaparin": "anticoagulant_lmwh",
    "lovenox": "anticoagulant_lmwh",
    # Pain / NSAID
    "ibuprofen": "nsaid_nephrotox",
    "naproxen": "nsaid_nephrotox",
    "ketorolac": "nsaid_nephrotox",
    "acetaminophen": "analgesic",
    # Psych / antiemetic
    "citalopram": "ssri_qt_prolong",
    "escitalopram": "ssri_qt_prolong",
    "ondansetron": "antiemetic_qt_prolong",
    "metoclopramide": "antiemetic",
    # Endocrine
    "insulin": "insulin",
    "metformin": "biguanide",
    # Other
    "contrast": "iodinated_contrast_nephrotox",
    # GI / fluids
    "pantoprazole": "ppi",
    "protonix": "ppi",
    "esomeprazole": "ppi",
    "nexium": "ppi",
    "famotidine": "h2_blocker",
    # Withdrawal / sedation
    "lorazepam": "benzodiazepine",
    "ativan": "benzodiazepine",
    "diazepam": "benzodiazepine",
    "valium": "benzodiazepine",
    "chlordiazepoxide": "benzodiazepine",
    "thiamine": "vitamin",
    "olanzapine": "antipsychotic_qt_prolong",
    # COPD
    "albuterol": "bronchodilator",
    "ipratropium": "bronchodilator",
    "duoneb": "bronchodilator",
    "combivent": "bronchodilator",
    "prednisone": "corticosteroid",
    "methylprednisolone": "corticosteroid",
    "solu-medrol": "corticosteroid",
    "dexamethasone": "corticosteroid",
    # Hyperkalemia
    "kayexalate": "k_binder",
    "patiromer": "k_binder",
    # Anesthesia / sedation
    "propofol": "sedative",
    "midazolam": "benzodiazepine",
    "versed": "benzodiazepine",
    "fentanyl": "opioid",
    "morphine": "opioid",
    "hydromorphone": "opioid",
    "dilaudid": "opioid",
    "oxycodone": "opioid",
    # Vasoactive
    "norepinephrine": "vasopressor",
    "vasopressin": "vasopressor",
    "epinephrine": "vasopressor",
    "phenylephrine": "vasopressor",
    "nicardipine": "antihypertensive",
    "labetalol": "antihypertensive",
}

# NOTE: physical therapy (PT) and case management are routed through the
# dispo signals, not the consult signals — clinically they're discharge
# enablers, not specialist consults that block care.
CONSULT_PATTERNS: List[Tuple[str, Pattern]] = [
    ("cardiology", re.compile(r"\bcardiology\b", re.I)),
    ("neurology", re.compile(r"\bneurology\b", re.I)),
    ("nephrology", re.compile(r"\bnephrology\b", re.I)),
    ("orthopedics", re.compile(r"\b(orthopedi[ac]s?|ortho)\b", re.I)),
    ("psychiatry", re.compile(r"\bpsychiatry\b", re.I)),
    ("infectious_disease", re.compile(r"\binfectious\s+disease\b", re.I)),
    ("surgery", re.compile(r"\b(surgery|surgical\s+team)\b", re.I)),
    ("gi", re.compile(r"\bGI\s+consult\b", re.I)),
]

CONSULT_PENDING_HINTS: List[Pattern] = [
    re.compile(r"awaiting\s+(callback|note|eval|consult)", re.I),
    re.compile(r"no\s+(eval|note)\s+(in\s+chart|yet)", re.I),
    re.compile(r"not\s+yet\s+(seen|evaluated|cleared)", re.I),
    re.compile(r"requested\s+\d+\s*(h|hours?|days?)\s+ago", re.I),
    re.compile(r"placed\s+yesterday", re.I),
]

IMAGING_PATTERNS: List[Tuple[str, Pattern]] = [
    ("ct", re.compile(r"\bCT\b\s*(?:abd|pelvis|head|chest|brain|abdomen)?", re.I)),
    ("mri", re.compile(r"\bMRI\b\s*(?:brain|head|spine)?", re.I)),
    ("xray", re.compile(r"\b(CXR|chest\s+x-?ray|pelvis\s+XR|XR)\b", re.I)),
    ("us", re.compile(r"\b(ultrasound|US)\b", re.I)),
    ("echo", re.compile(r"\b(echocardiogram|echo)\b", re.I)),
]

IMAGING_PENDING_HINTS: List[Pattern] = [
    re.compile(r"(pending|in\s+queue|scheduled\s+for|ordered\s+\d+\s*h)", re.I),
    re.compile(r"awaiting\s+(CT|MRI|imaging|study)", re.I),
]

DISPO_BLOCKERS: List[Tuple[str, Pattern]] = [
    ("snf_placement", re.compile(r"SNF\s+(placement|declined|backlog)", re.I)),
    ("home_oxygen", re.compile(r"home\s+(O2|oxygen)\s+(setup|ordered|backlog|training)", re.I)),
    ("insurance_auth", re.compile(r"insurance\s+(auth|authorization)", re.I)),
    ("dme_delay", re.compile(r"\bDME\s+(vendor|backlog|delay)", re.I)),
    ("pt_clearance", re.compile(r"\b(PT|physical\s+therapy)\b\s+(eval|to\s+clear|clearance|not\s+yet\s+seen)", re.I)),
    ("case_mgmt_pending", re.compile(r"case\s+management\s+(following|to|notes|delay)", re.I)),
    ("social_placement", re.compile(r"(no\s+family\s+support|intermittent\s+housing|lives\s+alone)", re.I)),
    ("training_incomplete", re.compile(r"(family\s+training|equipment\s+training)\s+not\s+yet", re.I)),
    ("medically_ready", re.compile(r"medically\s+(ready|optimized)", re.I)),
]

READMIT_RISK_HINTS: List[Pattern] = [
    re.compile(r"third\s+(admission|DKA|readmission)", re.I),
    re.compile(r"second\s+(admission|readmission)\s+in\s+\d+", re.I),
    re.compile(r"non-?adherence", re.I),
    re.compile(r"running\s+out\s+of\s+(insulin|medication)", re.I),
    re.compile(r"no\s+(PCP\s+follow-?up|outpatient)", re.I),
    re.compile(r"intermittent\s+housing", re.I),
    re.compile(r"unable\s+to\s+(weigh|afford|access)", re.I),
]

SYMPTOM_PATTERNS: List[Tuple[str, Pattern]] = [
    ("chest_pain", re.compile(r"chest\s+(pain|pressure|tightness|discomfort)", re.I)),
    ("dyspnea", re.compile(r"\b(dyspnea|shortness\s+of\s+breath|SOB)\b", re.I)),
    ("hypoxia", re.compile(r"hypox(ia|ic)", re.I)),
    ("altered_mental_status", re.compile(r"(altered\s+mental\s+status|confusion|AMS)", re.I)),
    ("hypotension", re.compile(r"\bhypotension\b", re.I)),
    ("fever", re.compile(r"\bfever\b", re.I)),
    ("seizure", re.compile(r"\bseizure\b", re.I)),
    ("syncope", re.compile(r"\bsyncope\b", re.I)),
    ("hemiparesis", re.compile(r"\b(hemiparesis|hemiplegia|facial\s+droop)\b", re.I)),
    ("melena", re.compile(r"\bmelena\b", re.I)),
    ("hematemesis", re.compile(r"\b(hematemesis|coffee[- ]ground\s+emesis)\b", re.I)),
    ("suicidal_ideation", re.compile(r"\b(suicidal|SI\b)", re.I)),
    ("tremor", re.compile(r"\btremor\b", re.I)),
    ("diaphoresis", re.compile(r"\bdiaphor(?:esis|etic)\b", re.I)),
]

CODE_STATUS_PATTERNS: List[Tuple[str, Pattern]] = [
    ("full_code", re.compile(r"\bfull\s+code\b", re.I)),
    ("dnr", re.compile(r"\bDNR\b", re.I)),
    ("dni", re.compile(r"\bDNI\b", re.I)),
    ("comfort_care", re.compile(r"\b(comfort\s+(care|measures\s+only)|CMO)\b", re.I)),
]

MOBILITY_PATTERNS: List[Tuple[str, Pattern]] = [
    ("bedbound", re.compile(r"\bbed-?bound\b", re.I)),
    ("walks_with_assist", re.compile(r"walks?\s+with\s+(assist|walker|cane)", re.I)),
    ("independent_amb", re.compile(r"\bambulating\s+(independently|without\s+assist)\b", re.I)),
    ("unable_to_ambulate", re.compile(r"unable\s+to\s+(bear\s+weight|ambulate)", re.I)),
    ("fall_risk", re.compile(r"\bfall\s+risk\b", re.I)),
]

PAIN_PATTERNS: List[Tuple[str, Pattern]] = [
    ("pain_scale", re.compile(r"pain\s+(?:scale\s+)?(\d{1,2})\s*/\s*10", re.I)),
    ("severe_pain", re.compile(r"\b(severe|excruciating|10/10)\s+pain", re.I)),
    ("controlled_pain", re.compile(r"pain\s+(controlled|well[- ]managed)", re.I)),
]

ADVANCE_DIRECTIVE_PATTERNS: List[Tuple[str, Pattern]] = [
    ("advance_directive_present", re.compile(r"\b(advance\s+directive|POLST|MOLST)\b", re.I)),
    ("hcp_designated", re.compile(r"\b(healthcare\s+proxy|HCP|surrogate\s+decision-?maker)\b", re.I)),
]

SOCIAL_PATTERNS: List[Tuple[str, Pattern]] = [
    ("homeless", re.compile(r"\b(homeless|unhoused|sheltered\s+housing)\b", re.I)),
    ("intermittent_housing", re.compile(r"intermittent\s+housing", re.I)),
    ("language_barrier", re.compile(r"(Mandarin|Spanish|Cantonese|Russian|Vietnamese)-?speaking\s+only", re.I)),
    ("lives_alone", re.compile(r"\blives\s+alone\b", re.I)),
    ("family_support_limited", re.compile(r"no\s+family\s+support", re.I)),
    ("primary_caregiver", re.compile(r"primary\s+caregiver", re.I)),
]


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def _scan(note: str, patterns: List[Tuple[str, Pattern]], kind: str) -> List[Finding]:
    out: List[Finding] = []
    seen: set[Tuple[str, int, int]] = set()
    for label, pat in patterns:
        for m in pat.finditer(note):
            key = (label, m.start(), m.end())
            if key in seen:
                continue
            seen.add(key)
            value = m.group(1) if m.groups() else None
            out.append(
                Finding(
                    kind=kind,
                    label=label,
                    value=value.strip() if isinstance(value, str) else None,
                    evidence=Span(m.start(), m.end(), m.group(0)),
                )
            )
    return out


def _scan_meds(note: str) -> List[Finding]:
    out: List[Finding] = []
    lower = note.lower()
    for med, klass in MEDICATIONS.items():
        # word boundary on both sides; case-insensitive
        for m in re.finditer(rf"\b{re.escape(med)}\b", lower):
            out.append(
                Finding(
                    kind="med",
                    label=med,
                    value=None,
                    evidence=Span(m.start(), m.end(), note[m.start():m.end()]),
                    metadata={"class": klass},
                )
            )
    return out


def _scan_consults(note: str) -> List[Finding]:
    out: List[Finding] = []
    lower = note.lower()
    pending = any(p.search(note) for p in CONSULT_PENDING_HINTS)
    for label, pat in CONSULT_PATTERNS:
        for m in pat.finditer(note):
            # heuristic: if "consult" appears within ~80 chars of the service
            # name OR a pending hint exists in the note, treat as a consult
            # signal. This avoids flagging stray words.
            window = note[max(0, m.start() - 80): m.end() + 80].lower()
            is_consult = (
                "consult" in window
                or "notified" in window
                or "to see" in window
                or "aware" in window
                or pending
            )
            if not is_consult:
                continue
            status = "pending" if any(p.search(window) for p in CONSULT_PENDING_HINTS) else "documented"
            out.append(
                Finding(
                    kind="consult",
                    label=label,
                    value=status,
                    evidence=Span(m.start(), m.end(), m.group(0)),
                    metadata={"status": status},
                )
            )
    return out


def _scan_imaging(note: str) -> List[Finding]:
    out: List[Finding] = []
    pending_global = any(p.search(note) for p in IMAGING_PENDING_HINTS)
    for label, pat in IMAGING_PATTERNS:
        for m in pat.finditer(note):
            window = note[max(0, m.start() - 60): m.end() + 80]
            window_pending = any(p.search(window) for p in IMAGING_PENDING_HINTS)
            status = "pending" if (window_pending or pending_global and "result" not in window.lower()) else "documented"
            # If the result is reported (e.g., "CXR with right lower lobe consolidation"),
            # prefer documented.
            if re.search(rf"{label}\b\s*(with|shows?|confirms?|demonstrates?|no\s+\w)", window, re.I):
                status = "documented"
            out.append(
                Finding(
                    kind="imaging",
                    label=label,
                    value=status,
                    evidence=Span(m.start(), m.end(), m.group(0)),
                    metadata={"status": status},
                )
            )
    return out


def _scan_dispo(note: str) -> List[Finding]:
    return _scan(note, DISPO_BLOCKERS, kind="dispo")


def _scan_symptoms(note: str) -> List[Finding]:
    return _scan(note, SYMPTOM_PATTERNS, kind="symptom")


def _scan_readmit(note: str) -> List[Finding]:
    out: List[Finding] = []
    for pat in READMIT_RISK_HINTS:
        for m in pat.finditer(note):
            out.append(
                Finding(
                    kind="risk_factor",
                    label="readmission_risk_marker",
                    value=None,
                    evidence=Span(m.start(), m.end(), m.group(0)),
                )
            )
    return out


@dataclass
class ExtractionResult:
    vitals: List[Finding]
    labs: List[Finding]
    meds: List[Finding]
    consults: List[Finding]
    imaging: List[Finding]
    dispo: List[Finding]
    symptoms: List[Finding]
    risk_factors: List[Finding]
    code_status: List[Finding] = field(default_factory=list)
    mobility: List[Finding] = field(default_factory=list)
    pain: List[Finding] = field(default_factory=list)
    advance_directives: List[Finding] = field(default_factory=list)
    social: List[Finding] = field(default_factory=list)

    def all_findings(self) -> List[Finding]:
        return (
            self.vitals + self.labs + self.meds + self.consults
            + self.imaging + self.dispo + self.symptoms + self.risk_factors
            + self.code_status + self.mobility + self.pain
            + self.advance_directives + self.social
        )

    def to_dict(self) -> Dict:
        def _serialize(items: List[Finding]) -> List[Dict]:
            return [
                {
                    "kind": f.kind,
                    "label": f.label,
                    "value": f.value,
                    "evidence": asdict(f.evidence),
                    "metadata": f.metadata,
                }
                for f in items
            ]

        return {
            "vitals": _serialize(self.vitals),
            "labs": _serialize(self.labs),
            "meds": _serialize(self.meds),
            "consults": _serialize(self.consults),
            "imaging": _serialize(self.imaging),
            "dispo": _serialize(self.dispo),
            "symptoms": _serialize(self.symptoms),
            "risk_factors": _serialize(self.risk_factors),
            "code_status": _serialize(self.code_status),
            "mobility": _serialize(self.mobility),
            "pain": _serialize(self.pain),
            "advance_directives": _serialize(self.advance_directives),
            "social": _serialize(self.social),
        }


def extract(note: str) -> ExtractionResult:
    return ExtractionResult(
        vitals=_scan(note, VITAL_PATTERNS, "vital"),
        labs=_scan(note, LAB_PATTERNS, "lab"),
        meds=_scan_meds(note),
        consults=_scan_consults(note),
        imaging=_scan_imaging(note),
        dispo=_scan_dispo(note),
        symptoms=_scan_symptoms(note),
        risk_factors=_scan_readmit(note),
        code_status=_scan(note, CODE_STATUS_PATTERNS, "code_status"),
        mobility=_scan(note, MOBILITY_PATTERNS, "mobility"),
        pain=_scan(note, PAIN_PATTERNS, "pain"),
        advance_directives=_scan(note, ADVANCE_DIRECTIVE_PATTERNS, "advance_directive"),
        social=_scan(note, SOCIAL_PATTERNS, "social"),
    )
