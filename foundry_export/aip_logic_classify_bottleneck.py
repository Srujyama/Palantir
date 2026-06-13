"""
`classify_bottleneck` — Foundry Functions (Python) artifact for Bottleneck Radar.

WHAT THIS IS
    A complete, self-contained, executable port of the local backend's
    decision path:

        extract signals  ->  evaluate 12 protocols  ->  screen 13 interaction
        rules  ->  cascading bottleneck classifier (subsumption + tie-break)

    One file, stdlib only (``re`` + ``dataclasses``), zero imports from the
    local ``app/*`` packages. Everything the rules need — med classes,
    interaction rule table, protocol library, negation cues, cascade order —
    is carried as a frozen copy inside this module.

REGISTRATION (Functions repo / AIP Logic)
    Drop this module into a Python Functions repository and add the thin
    wrapper below; the body is already the typed entry point.

        # src/bottleneck/function.py  (Functions repo)
        from functions.api import function
        from bottleneck.aip_logic_classify_bottleneck import classify_bottleneck

        @function
        def classify_bottleneck_fn(note_text: str, age: int) -> dict:
            return classify_bottleneck(note_text, age)

    Bind the published function to the `Patient` object type so AIP Logic /
    Workshop can invoke it per patient (`note_text` comes from the linked
    `Note` object, `age` from the Patient). The function is pure and
    deterministic: same note in, same answer out, every time.

WRITEBACK (Bottleneck object set)
    The returned dict maps 1:1 onto the `Bottleneck` object type from
    `01_ontology_spec.md` (primary key `patient_id` is supplied by the bound
    Patient at the Logic layer, not computed here):

        category | urgency | owner | protocol_key | evidence_span | summary

    plus two display properties the Workshop bottleneck card uses
    (`03_workshop_storyboard.md`): `recommended_action` and `citation`.
    Materialize via an ontology edit in the Logic block (one active
    Bottleneck per patient — upsert on patient_id), or via a writeback
    dataset backing the object set. Re-running the function re-materializes
    the object; see `05_automations_spec.md` automation (c).

POSITION — NO LLM IN THIS PATH
    This function is the recommendation path, and it contains no model call
    of any kind. Category, urgency, owner, recommended action, and citation
    all come from the deterministic rule tables below, and every output
    traces to a literal span of the source note (`evidence_span`). LLMs in
    this deployment are confined to upstream signal extraction convenience
    (Pipeline 1 in `02_pipeline_and_function_spec.md`) and to the
    conversational layer (`04_aip_agent_spec.md`), which can only *read*
    what this function wrote. That is the line that holds the AIP Use Case
    Restriction position for clinical settings: operational coordination
    tool, not a clinical decision aid. All data notional.

PARITY GUARANTEE
    `backend/tests/test_aip_logic_parity.py` loads this file by path and
    asserts that (category, urgency, owner) matches the live backend
    `app.services.bottleneck.classify()` on every one of the 176 corpus
    notes. If you edit a frozen section, run that test.

NOTE ON `age`
    Accepted to match the Patient object binding. The current rule cascade
    does not branch on age; it is reserved for age-gated routing policies
    and kept in the signature so adding one later is not a breaking change.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Pattern, Tuple

__all__ = ["classify_bottleneck"]


# ===========================================================================
# SECTION 1 — Signal extraction
# FROZEN COPY of app/nlp/extractor.py (subset) — see test_aip_logic_parity.py
#
# Only the surfaces the classifier consumes are carried: labs, meds,
# consults, imaging, dispo blockers, symptoms, readmission-risk markers.
# Vitals / code status / mobility / pain / social are extracted locally for
# display but never read by the decision path, so they are not ported.
# ===========================================================================

@dataclass
class Span:
    start: int
    end: int
    text: str


@dataclass
class Finding:
    kind: str                  # lab | med | consult | imaging | dispo | symptom | risk_factor
    label: str
    value: Optional[str]
    evidence: Span
    metadata: Dict[str, object] = field(default_factory=dict)


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
# checks. Dict ORDER matters: it sets med-scan iteration order, which feeds
# the interaction engine's distinct-drug assignment. Do not reorder.
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

CONSULT_PATTERNS: List[Tuple[str, Pattern]] = [
    ("cardiology", re.compile(r"\bcardiology\b", re.I)),
    ("neurology", re.compile(r"\bneurology\b", re.I)),
    ("nephrology", re.compile(r"\bnephrology\b", re.I)),
    ("orthopedics", re.compile(r"\b(orthopedi[ac]s?|ortho)\b", re.I)),
    ("psychiatry", re.compile(r"\bpsychiatry\b", re.I)),
    ("infectious_disease", re.compile(r"\binfectious\s+disease\b", re.I)),
    ("surgery", re.compile(r"\b(surgery|surgical\s+(?:team|consult|service|eval))\b", re.I)),
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
    # "US" must stay case-sensitive (uppercase) so the English word "us"
    # never registers as an ultrasound order.
    ("us", re.compile(r"(?i:\bultrasound\b)|\bUS\b")),
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

# --- Negation tagging (NegEx-lite) -----------------------------------------
# A finding whose evidence sits near a negation cue in the SAME sentence is
# tagged metadata["negated"] = True. Findings are never dropped: downstream
# consumers (the interaction engine) filter on the flag.

NEGATION_PRE_CUES: List[Pattern] = [
    re.compile(r"\bdenie[sd]\b", re.I),
    re.compile(r"\bdenying\b", re.I),
    re.compile(r"\bno\s+evidence\s+of\b", re.I),
    re.compile(r"\bnegative\s+for\b", re.I),
    re.compile(r"\bwithout\b", re.I),
    re.compile(r"\bruled\s+out\b", re.I),
    re.compile(r"\bno\s+signs?\s+of\b", re.I),
    re.compile(r"\bnot\s+on\b", re.I),
    re.compile(r"\boff\s+(?:of\s+)?", re.I),
    re.compile(r"\bdiscontinued?\b", re.I),
    re.compile(r"\bd/?c'?d\b", re.I),
    re.compile(r"\bstopp(?:ed|ing)\b", re.I),
    re.compile(r"\bh[eo]ld(?:ing)?\b", re.I),
    re.compile(r"\bno\b", re.I),        # standalone token: "no melena"
    re.compile(r"\bnot\b", re.I),
    re.compile(r"\bnever\b", re.I),
    re.compile(r"\bfree\s+of\b", re.I),
]

NEGATION_POST_CUES: List[Pattern] = [
    re.compile(r"\bheld\b", re.I),
    re.compile(r"\bon\s+hold\b", re.I),
    re.compile(r"\bdiscontinued\b", re.I),
    re.compile(r"\bd/?c'?d\b", re.I),
    re.compile(r"\bstopped\b", re.I),
    re.compile(r"\bruled\s+out\b", re.I),
    re.compile(r"\bnot\s+(?:given|administered|started|present)\b", re.I),
]

_EXTRACTOR_SENTENCE_BOUNDARY = re.compile(r"[.!?;\n]")
_NEGATION_WINDOW_CHARS = 40


def _is_negated(note: str, span: Span) -> bool:
    pre = note[max(0, span.start - _NEGATION_WINDOW_CHARS): span.start]
    pre = _EXTRACTOR_SENTENCE_BOUNDARY.split(pre)[-1]          # same sentence only
    if any(cue.search(pre) for cue in NEGATION_PRE_CUES):
        return True
    post = note[span.end: span.end + _NEGATION_WINDOW_CHARS]
    post = _EXTRACTOR_SENTENCE_BOUNDARY.split(post)[0]         # same sentence only
    return any(cue.search(post) for cue in NEGATION_POST_CUES)


def _tag_negation(note: str, findings: List[Finding]) -> List[Finding]:
    for f in findings:
        if _is_negated(note, f.evidence):
            f.metadata["negated"] = True
    return findings


def _scan(note: str, patterns: List[Tuple[str, Pattern]], kind: str) -> List[Finding]:
    out: List[Finding] = []
    seen: set = set()
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
    pending = any(p.search(note) for p in CONSULT_PENDING_HINTS)
    for label, pat in CONSULT_PATTERNS:
        for m in pat.finditer(note):
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
            status = "pending" if ((window_pending or pending_global) and "result" not in window.lower()) else "documented"
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
    """Subset of the local ExtractionResult: only the surfaces the decision
    path reads. Field semantics are identical to app/nlp/extractor.py."""
    labs: List[Finding]
    meds: List[Finding]
    consults: List[Finding]
    imaging: List[Finding]
    dispo: List[Finding]
    symptoms: List[Finding]
    risk_factors: List[Finding]


def extract(note: str) -> ExtractionResult:
    return ExtractionResult(
        labs=_scan(note, LAB_PATTERNS, "lab"),
        meds=_tag_negation(note, _scan_meds(note)),
        consults=_scan_consults(note),
        imaging=_scan_imaging(note),
        dispo=_scan(note, DISPO_BLOCKERS, "dispo"),
        symptoms=_tag_negation(note, _scan(note, SYMPTOM_PATTERNS, "symptom")),
        risk_factors=_scan_readmit(note),
    )


# ===========================================================================
# SECTION 2 — Care-pathway protocol library (12 protocols)
# FROZEN COPY of app/protocols/library.py — see test_aip_logic_parity.py
#
# In Foundry these rows also live as the Protocol / ProtocolStep object sets
# (protocols.csv); this frozen copy is what makes the function self-contained
# so it cannot drift from the version the parity test pinned.
# ===========================================================================

@dataclass(frozen=True)
class Protocol:
    key: str
    name: str
    triggers: List[str]
    expected_actions: List["ExpectedAction"]
    time_window_hours: int
    owner: str
    urgency_if_incomplete: str           # red | amber | green
    citation: str


@dataclass(frozen=True)
class ExpectedAction:
    key: str
    label: str
    documented_patterns: List[str]
    severity: str = "required"           # required | recommended


SEPSIS = Protocol(
    key="sepsis",
    name="Surviving Sepsis Hour-1 Bundle",
    triggers=[
        r"\bsepsis\b", r"\bseptic\b", r"\bSIRS\b",
        # A bare lactate only auto-fires the hour-1 bundle at the septic-shock
        # threshold (>= 4). A moderate lactate (2-3.9) without sepsis / SIRS
        # language does not by itself owe the bundle.
        r"lactate\s*[>:]?\s*(?:[4-9]|[1-9]\d)(?:\.\d)?",
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
                r"broad-?spectrum\s+(antibiotics?|abx)",
                r"\b(vancomycin|piperacillin|tazobactam|cefepime|meropenem|ceftriaxone|zosyn|cefazolin|levofloxacin|azithromycin|ciprofloxacin)\b",
            ],
        ),
        ExpectedAction(
            "fluids",
            "Begin 30 mL/kg crystalloid resuscitation",
            [r"30\s*mL/kg", r"fluid\s+bolus", r"IV\s+fluids?\s+(initiated|bolus|running)", r"\bIVF\b"],
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
        r"community-?acquired\s+pneumonia", r"\bCAP\b",
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
            [
                r"potassium\s+(repletion|replacement|added|repleted|replaced)",
                r"\bKCl\b",
                r"replet\w*\s+K\b",
                r"\bK\s+(rider|repletion|replacement|repleted|replaced)\b",
            ],
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


PE = Protocol(
    key="pe",
    name="Pulmonary Embolism Initial Management",
    triggers=[
        r"\bpulmonary\s+embol",
        r"(suspected|confirmed|diagnosed|acute)\s+PE\b",
        r"\bPE\b\s*(suspected|confirmed|diagnosed)",
        r"confirms?\s+(bilateral\s+)?(segmental\s+|subsegmental\s+)?PE\b",
        r"\bCTPA\s+(positive|confirms)",
        r"right\s+heart\s+strain", r"submassive\s+PE\b", r"massive\s+PE\b",
    ],
    expected_actions=[
        ExpectedAction(
            "anticoag",
            "Therapeutic anticoagulation initiated",
            [
                r"\b(heparin|enoxaparin|lovenox|apixaban|rivaroxaban)\b",
                r"therapeutic\s+anticoagulation",
            ],
        ),
        ExpectedAction(
            "imaging",
            "Confirmatory CT-PA or VQ scan",
            [r"CT-?PA", r"V/?Q\s+scan", r"pulmonary\s+angiogram"],
        ),
        ExpectedAction(
            "risk_stratify",
            "Risk stratification (RV strain, troponin, BNP)",
            [
                r"\btroponin\b", r"\bBNP\b", r"echocardiogram",
                r"RV\s+(strain|dysfunction|dilation)",
            ],
        ),
        ExpectedAction(
            "monitor",
            "Telemetry / continuous monitoring",
            [r"telemetry", r"continuous\s+monitoring", r"\bICU\b"],
        ),
    ],
    time_window_hours=2,
    owner="physician",
    urgency_if_incomplete="red",
    citation="ESC/AHA Pulmonary Embolism Guidelines",
)


GI_BLEED = Protocol(
    key="gi_bleed",
    name="Upper GI Bleed Initial Management",
    triggers=[
        r"\bGIB\b", r"GI\s+bleed", r"melena",
        r"hematemesis", r"coffee-?ground\s+emesis",
        r"hemoglobin\s+drop", r"hgb\s+(dropped|decreased)\s+to",
    ],
    expected_actions=[
        ExpectedAction(
            "ivf_access",
            "Two large-bore IV access + IV fluids",
            [
                r"\btwo\s+large-?bore\b", r"large-?bore\s+IV",
                r"IV\s+fluids?\s+(running|bolus|initiated)",
            ],
        ),
        ExpectedAction(
            "type_screen",
            "Type and screen / type and cross",
            [r"type\s+and\s+(screen|cross)", r"\bT&S\b", r"\bT&C\b"],
        ),
        ExpectedAction(
            "ppi",
            "IV proton-pump inhibitor",
            [r"\b(pantoprazole|protonix|esomeprazole|nexium)\b", r"\bPPI\b\s+(drip|infusion)"],
        ),
        ExpectedAction(
            "gi_consult",
            "GI consult / endoscopy plan",
            [
                r"\bGI\s+(consult|notified|aware|to\s+see)",
                r"\bendoscopy\b", r"\bEGD\b",
            ],
        ),
    ],
    time_window_hours=2,
    owner="physician",
    urgency_if_incomplete="red",
    citation="ACG Upper GI Bleed Guidelines",
)


AKI = Protocol(
    key="aki",
    name="Acute Kidney Injury Workup",
    triggers=[
        r"\bAKI\b", r"acute\s+kidney\s+injury",
        r"creatinine\s+(rising|rose|increased|elevated)",
        r"creatinine\s+(from\s+)?[01]\.\d\s+to\s+[2-9]",
        r"UOP\s*<", r"oliguria", r"anuria",
    ],
    expected_actions=[
        ExpectedAction(
            "med_review",
            "Medication review for nephrotoxins",
            [
                r"h[eo]ld\w*\s+(NSAIDs?|ibuprofen|naproxen|ACE\w*|ARBs?|lisinopril|losartan"
                r"|vancomycin|tobramycin|gentamicin|aminoglycosides?|contrast|nephrotoxi\w+)",
                r"nephrotoxic\s+(review|hold|stop)",
                r"pharmacy\s+review",
                r"renal\s+dosing",
            ],
        ),
        ExpectedAction(
            "volume_assessment",
            "Volume status assessment",
            [
                r"\b(euvolemic|hypovolemic|hypervolemic)\b",
                r"\bJVP\b", r"orthostatic",
                r"fluid\s+(challenge|trial|bolus)",
            ],
        ),
        ExpectedAction(
            "urine_studies",
            "Urine studies (FENa, sediment, electrolytes)",
            [r"\bFENa\b", r"urine\s+(sediment|electrolytes|sodium)", r"muddy\s+brown"],
        ),
        ExpectedAction(
            "renal_us",
            "Renal ultrasound to evaluate obstruction",
            [r"renal\s+(US|ultrasound)", r"\bhydronephrosis\b"],
        ),
    ],
    time_window_hours=12,
    owner="physician",
    urgency_if_incomplete="amber",
    citation="KDIGO Acute Kidney Injury Guidelines",
)


CIWA = Protocol(
    key="ciwa",
    name="Alcohol Withdrawal (CIWA-Ar Protocol)",
    triggers=[
        r"alcohol\s+(withdrawal|use\s+disorder)",
        r"\bCIWA\b", r"last\s+drink\s+\d",
        r"history\s+of\s+(DTs|delirium\s+tremens|withdrawal\s+seizures?)",
        r"\bAUD\b",
    ],
    expected_actions=[
        ExpectedAction(
            "ciwa_scoring",
            "CIWA-Ar scoring documented q1-2h",
            [r"CIWA(-Ar)?\s+(score|scoring|q\d)", r"withdrawal\s+scoring"],
        ),
        ExpectedAction(
            "benzo",
            "Benzodiazepine protocol (symptom-triggered)",
            [
                r"\b(lorazepam|ativan|diazepam|valium|chlordiazepoxide|librium)\b",
                r"benzodiazepine\s+(taper|protocol|drip)",
                r"symptom-?triggered",
            ],
        ),
        ExpectedAction(
            "thiamine",
            "Thiamine + multivitamin (banana bag)",
            [r"\bthiamine\b", r"banana\s+bag", r"\bIV\s+B-?complex\b"],
        ),
        ExpectedAction(
            "seizure_precautions",
            "Seizure precautions and monitoring",
            [r"seizure\s+(precautions|monitoring|watch)", r"padded\s+rails"],
        ),
    ],
    time_window_hours=2,
    owner="physician",
    urgency_if_incomplete="amber",
    citation="ASAM Alcohol Withdrawal Management Guidelines",
)


NEUTROPENIC_FEVER = Protocol(
    key="neutropenic_fever",
    name="Neutropenic Fever Empiric Management",
    triggers=[
        r"neutropenic\s+fever",
        r"\bANC\s*[<:]?\s*\d{1,3}\b",
        r"ANC\s+(of\s+)?\d{1,3}\b",
        r"febrile\s+neutropenia",
        r"chemo(therapy)?.{0,40}fever",
        r"fever.{0,40}(chemo|induction|neutropenic)",
    ],
    expected_actions=[
        ExpectedAction(
            "antibiotics",
            "Empiric broad-spectrum antibiotics within 60 min",
            [
                r"\b(cefepime|piperacillin|tazobactam|zosyn|meropenem|imipenem)\b",
                r"empiric\s+(antibiotics?|abx)",
            ],
        ),
        ExpectedAction(
            "blood_cx",
            "Blood cultures x2 (including from line)",
            [r"blood\s+cultures?\s+x\s*2", r"cultures\s+from\s+(line|port|central)"],
        ),
        ExpectedAction(
            "isolation",
            "Neutropenic precautions / isolation",
            [r"neutropenic\s+(precautions|isolation)", r"reverse\s+isolation"],
        ),
        ExpectedAction(
            "oncology_notified",
            "Oncology team notified",
            [r"oncology\s+(notified|consult|aware|to\s+see)", r"primary\s+oncologist"],
        ),
    ],
    time_window_hours=1,
    owner="physician",
    urgency_if_incomplete="red",
    citation="IDSA Febrile Neutropenia Guidelines",
)


HYPERKALEMIA = Protocol(
    key="hyperkalemia",
    name="Severe Hyperkalemia Treatment",
    triggers=[
        r"\bK\s*[: ]?\s*([6-9]\.\d|\d{2}\.\d)",
        r"hyperkalemia",
        r"potassium\s+(elevated|high|of)\s+\d",
        r"peaked\s+T-?waves?",
    ],
    expected_actions=[
        ExpectedAction(
            "ecg",
            "ECG to assess for hyperkalemic changes",
            [r"\b(ECG|EKG)\b", r"peaked\s+T", r"\bQRS\s+widening\b"],
        ),
        ExpectedAction(
            "stabilize_membrane",
            "Calcium gluconate / chloride for membrane stabilization",
            [r"calcium\s+(gluconate|chloride)", r"\bIV\s+calcium\b"],
        ),
        ExpectedAction(
            "shift_intracellular",
            "Insulin + dextrose to shift potassium intracellularly",
            [
                r"insulin\s+(and|\+)\s+(D50|dextrose|glucose)",
                r"D50.*insulin",
                r"\bbeta-?agonist\b", r"albuterol\s+nebulizer",
            ],
        ),
        ExpectedAction(
            "remove",
            "Removal: diuretic, kayexalate, or dialysis",
            [
                r"\b(furosemide|lasix|patiromer|kayexalate|sodium\s+polystyrene)\b",
                # "HD 3" / "HD #3" is hospital-day shorthand, not hemodialysis.
                r"\bdialysis\b", r"\bCRRT\b", r"\bHD\b(?!\s*#?\s*\d)",
            ],
        ),
    ],
    time_window_hours=1,
    owner="physician",
    urgency_if_incomplete="red",
    citation="ESC/AHA Hyperkalemia Management Consensus",
)


COPD = Protocol(
    key="copd",
    name="COPD Exacerbation Management",
    triggers=[
        r"COPD\s+exacerbation",
        r"acute\s+exacerbation\s+of\s+COPD",
        r"\bAECOPD\b",
        r"increased\s+(sputum|dyspnea).*COPD",
    ],
    expected_actions=[
        ExpectedAction(
            "bronchodilator",
            "Short-acting bronchodilators (DuoNeb / albuterol-ipratropium)",
            [
                r"\b(albuterol|ipratropium|duoneb|combivent|nebulizer)\b",
                r"bronchodilator",
            ],
        ),
        ExpectedAction(
            "steroids",
            "Systemic corticosteroids",
            [
                r"\b(prednisone|methylprednisolone|solu-?medrol|dexamethasone)\b",
                r"systemic\s+steroids",
            ],
        ),
        ExpectedAction(
            "antibiotics",
            "Antibiotics if sputum purulence increased",
            [
                r"\b(azithromycin|doxycycline|amoxicillin|levofloxacin)\b",
                r"antibiotic\s+for\s+exacerbation",
            ],
        ),
        ExpectedAction(
            "oxygen_target",
            "Controlled oxygen targeted SpO2 88-92%",
            [
                r"SpO2\s+(target|goal)\s+88",
                r"controlled\s+oxygen",
                r"titrate\s+(O2|oxygen)",
            ],
        ),
    ],
    time_window_hours=4,
    owner="physician",
    urgency_if_incomplete="amber",
    citation="GOLD COPD Strategy",
)


PROTOCOLS: List[Protocol] = [
    SEPSIS,
    ACS,
    STROKE,
    CAP,
    DKA,
    PE,
    GI_BLEED,
    AKI,
    CIWA,
    NEUTROPENIC_FEVER,
    HYPERKALEMIA,
    COPD,
]


# ===========================================================================
# SECTION 3 — Silent-failure detector (protocol gap evaluation)
# FROZEN COPY of app/services/silent_failure.py — see test_aip_logic_parity.py
# ===========================================================================

@dataclass
class SilentFailure:
    protocol_key: str
    protocol_name: str
    missing_action: str
    severity: str                     # required | recommended
    citation: str
    trigger_evidence: Span
    owner: str
    urgency: str


@dataclass
class ProtocolMatch:
    protocol: Protocol
    triggered: bool
    trigger_evidence: List[Span] = field(default_factory=list)
    documented: List[ExpectedAction] = field(default_factory=list)
    missing: List[ExpectedAction] = field(default_factory=list)


# Trigger-context cues, two families (cf. NegEx/ConText), both clipped to the
# trigger's own sentence. True negation cues are LEFT-only ("no melena",
# "denies chest pain"); historical / resolution cues apply on either side.
_NEGATION_TOKENS_LEFT = [
    "denies", "no ", "not ", "ruled out", "negative", "without", "free of",
]
_HISTORICAL_TOKENS = [
    "resolved", "improving", "improved", "history of", "h/o",
    "prior", "previous", "stable", "afebrile",
    "admitted", "days ago", "weeks ago", "last admission",
    "post-op", "post op", "second admission", "third admission",
]
_NEGATION_WINDOW = 60
_SENTENCE_BOUNDARY = re.compile(r"[.!?;\n]")

# Protocol-wide resolution phrases: the condition is already addressed /
# resolved / historical anywhere in the note.
_PROTOCOL_RESOLUTION_PHRASES = {
    "dka": [r"DKA\s+resolved", r"anion\s+gap\s+closed", r"gap\s+closed", r"bicarbonate\s+(2[0-9]|[3-9]\d)"],
    "sepsis": [r"sepsis\s+resolved", r"afebrile\s+for"],
    "stroke": [
        r"stroke\s+resolved", r"deficits\s+resolved",
        r"(stroke|tPA|thrombolysis)\s+window\s+(expired|closed|passed)",
    ],
    "cap": [r"pneumonia\s+(resolved|improving)"],
    "acs": [
        r"chest\s+pain\s+resolved", r"troponin\s+down-?trending",
        r"two\s+negative\s+troponins?", r"troponins?\s+x\s*2\s+negative",
        r"chest\s+pain.{0,40}ruled\s+out", r"non-?cardiac\s+chest\s+pain",
    ],
    "pe": [r"PE\s+resolved", r"clot\s+burden\s+(decreased|improving)"],
    "gi_bleed": [r"bleeding\s+(stopped|resolved)", r"hgb\s+(stable|recovered)"],
    "aki": [r"AKI\s+(resolved|improving)", r"creatinine\s+(returned|back\s+to\s+baseline)", r"renal\s+function\s+recovered"],
    "ciwa": [r"CIWA\s+(score|scores)\s+(<\s*8|low|0)", r"withdrawal\s+resolved"],
    "neutropenic_fever": [r"ANC\s+(recovered|>\s*500)", r"afebrile\s+for\s+\d+"],
    "hyperkalemia": [r"potassium\s+(normalized|corrected|back\s+to)", r"K\s+(3\.\d|4\.\d|5\.[0-2])"],
    "copd": [r"COPD\s+exacerbation,?\s+resolved", r"COPD\s+stable", r"back\s+to\s+baseline"],
}

# KDIGO-style severity gate for the AKI workup bundle: the full bundle is
# owed once AKI is established/severe (Cr >= 2.0, documented rise to >= 2.0,
# oliguria/anuria, ATN sediment). A mild bump is handled by the nephrotoxin
# med-review flag in the interaction engine instead.
_AKI_SEVERITY_CONTEXT: List[str] = [
    r"(?:creatinine|\bCr\b)\s*[: ]?\s*(?:[2-9]|[1-9]\d)\.\d",
    r"\bto\s+(?:[2-9]|[1-9]\d)\.\d",
    r"\bUOP\s*<", r"oliguri", r"anuri", r"muddy\s+brown",
]

# Short / non-specific triggers require corroborating context in the note.
_AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT: Dict[str, List[str]] = {
    r"\bCVA\b": ["stroke", "infarct", "tPA", "NIHSS", "hemiparesis", "aphasi", "facial droop"],
    r"\bAKI\b": _AKI_SEVERITY_CONTEXT,
    r"acute\s+kidney\s+injury": _AKI_SEVERITY_CONTEXT,
    r"creatinine\s+(rising|rose|increased|elevated)": _AKI_SEVERITY_CONTEXT,
}


def _is_negated_or_historical(note: str, span: Span) -> bool:
    left = note[max(0, span.start - _NEGATION_WINDOW): span.start].lower()
    left = _SENTENCE_BOUNDARY.split(left)[-1]    # same sentence only
    right = note[span.end: span.end + _NEGATION_WINDOW].lower()
    right = _SENTENCE_BOUNDARY.split(right)[0]   # same sentence only
    if any(tok in left for tok in _NEGATION_TOKENS_LEFT):
        return True
    return any(tok in left or tok in right for tok in _HISTORICAL_TOKENS)


def _ambiguous_trigger_passes(note: str, pattern: str, span: Span) -> bool:
    needs = _AMBIGUOUS_TRIGGERS_NEEDING_CONTEXT.get(pattern)
    if not needs:
        return True
    return any(re.search(kw, note, flags=re.IGNORECASE) for kw in needs)


def _find_first(note: str, patterns: List[str]) -> Optional[Span]:
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


def evaluate_protocols(note: str) -> List[ProtocolMatch]:
    """Per-protocol triggered/documented/missing breakdown for a note."""
    out: List[ProtocolMatch] = []
    for proto in PROTOCOLS:
        trig = _find_first(note, proto.triggers)
        if not trig or _protocol_resolved(note, proto.key):
            out.append(ProtocolMatch(protocol=proto, triggered=False))
            continue

        documented, missing = [], []
        for action in proto.expected_actions:
            if _any_match(note, action.documented_patterns):
                documented.append(action)
            else:
                missing.append(action)

        out.append(
            ProtocolMatch(
                protocol=proto,
                triggered=True,
                trigger_evidence=[trig],
                documented=documented,
                missing=missing,
            )
        )
    return out


def silent_failures(note: str, matches: Optional[List[ProtocolMatch]] = None) -> List[SilentFailure]:
    """Only the actionable misses across all triggered protocols."""
    out: List[SilentFailure] = []
    for pm in (matches if matches is not None else evaluate_protocols(note)):
        if not pm.triggered:
            continue
        for action in pm.missing:
            out.append(
                SilentFailure(
                    protocol_key=pm.protocol.key,
                    protocol_name=pm.protocol.name,
                    missing_action=action.label,
                    severity=action.severity,
                    citation=pm.protocol.citation,
                    trigger_evidence=pm.trigger_evidence[0] if pm.trigger_evidence else Span(0, 0, ""),
                    owner=pm.protocol.owner,
                    urgency=pm.protocol.urgency_if_incomplete,
                )
            )
    return out


# ===========================================================================
# SECTION 4 — Drug-interaction screening engine (13 citation-backed rules)
# FROZEN COPY of app/services/interactions.py — see test_aip_logic_parity.py
# ===========================================================================

SEVERITY_RANK: Dict[str, int] = {"red": 0, "amber": 1}

# Supplemental drug surface: drugs the extractor table does not carry.
SUPPLEMENTAL_MEDICATIONS: Dict[str, str] = {
    # Serotonergic agents missing from the extractor's surface
    "tramadol": "opioid_serotonergic",
    "linezolid": "antibiotic_maoi_serotonergic",
    "sertraline": "ssri",
    "fluoxetine": "ssri",
    "paroxetine": "ssri",
    "venlafaxine": "snri_serotonergic",
    "duloxetine": "snri_serotonergic",
    "trazodone": "serotonergic",
    "buspirone": "serotonergic",
    "sumatriptan": "triptan_serotonergic",
    # Thiazides (triple-whammy participation)
    "hydrochlorothiazide": "thiazide_diuretic",
    "chlorthalidone": "thiazide_diuretic",
    # Common brand names normalized via ALIASES below
    "eliquis": "anticoagulant_doac",
    "xarelto": "anticoagulant_doac",
    "coumadin": "anticoagulant_vka",
    "plavix": "antiplatelet",
    "ticagrelor": "antiplatelet",
    "prasugrel": "antiplatelet",
}

# Brand -> generic so one drug mentioned twice never satisfies a
# two-distinct-drug rule against itself.
ALIASES: Dict[str, str] = {
    "lovenox": "enoxaparin",
    "ativan": "lorazepam",
    "valium": "diazepam",
    "versed": "midazolam",
    "dilaudid": "hydromorphone",
    "protonix": "pantoprazole",
    "nexium": "esomeprazole",
    "zosyn": "piperacillin",
    "solu-medrol": "methylprednisolone",
    "eliquis": "apixaban",
    "xarelto": "rivaroxaban",
    "coumadin": "warfarin",
    "plavix": "clopidogrel",
}


@dataclass(frozen=True)
class ContextCondition:
    """Satisfied when ANY configured check holds on non-negated findings."""
    description: str
    lab: Optional[str] = None
    lab_gte: Optional[float] = None
    lab_lte: Optional[float] = None
    symptom: Optional[str] = None


@dataclass(frozen=True)
class InteractionRule:
    key: str
    name: str
    severity: str                                   # red | amber
    required_classes: Tuple[Tuple[str, ...], ...]   # groups of class substrings
    mechanism: str
    recommendation: str
    citation: str
    context_condition: Optional[ContextCondition] = None


@dataclass
class MedInvolved:
    name: str
    drug_class: str
    evidence: Span


@dataclass
class InteractionFlag:
    rule_key: str
    name: str
    severity: str
    mechanism: str
    recommendation: str
    citation: str
    meds_involved: List[MedInvolved]
    context_evidence: List[Span]


INTERACTION_RULES: Tuple[InteractionRule, ...] = (
    InteractionRule(
        key="nephrotoxic_combo_aki",
        name="Nephrotoxic exposure during AKI",
        severity="red",
        required_classes=(("nephrotox",),),
        context_condition=ContextCondition(
            description="creatinine >= 1.5", lab="creatinine", lab_gte=1.5,
        ),
        mechanism=(
            "Continued nephrotoxic exposure during acute kidney injury "
            "compounds tubular damage and delays renal recovery."
        ),
        recommendation=(
            "Hold or dose-adjust nephrotoxic agents; recheck BMP and "
            "trend creatinine."
        ),
        citation="KDIGO AKI guidance",
    ),
    InteractionRule(
        key="qt_prolonged_qtc",
        name="QT-prolonging agent with prolonged QTc",
        severity="red",
        required_classes=(("qt_prolong",),),
        context_condition=ContextCondition(
            description="QTc >= 500 ms", lab="QTc", lab_gte=500,
        ),
        mechanism=(
            "A QT-prolonging agent on top of a QTc at or above 500 ms "
            "sharply raises the risk of torsades de pointes."
        ),
        recommendation=(
            "Rationalize QT-prolonging agents; replete K and Mg; repeat ECG."
        ),
        citation="CredibleMeds QT drug list",
    ),
    InteractionRule(
        key="qt_stack",
        name="Multiple QT-prolonging agents",
        severity="amber",
        required_classes=(("qt_prolong",), ("qt_prolong",)),
        mechanism=(
            "Concurrent QT-prolonging medications have additive effect on "
            "repolarization and torsades de pointes risk."
        ),
        recommendation=(
            "Rationalize QT-prolonging agents; replete K and Mg; repeat ECG."
        ),
        citation="CredibleMeds QT drug list",
    ),
    InteractionRule(
        key="anticoag_active_bleed",
        name="Anticoagulant with active GI bleeding signs",
        severity="red",
        required_classes=(("anticoag",),),
        context_condition=ContextCondition(
            description="melena documented", symptom="melena",
        ),
        mechanism=(
            "Ongoing anticoagulation during an active GI bleed sustains "
            "blood loss and delays hemostasis."
        ),
        recommendation=(
            "Hold anticoagulant; type and screen; assess for reversal if "
            "bleeding is active."
        ),
        citation="ACCP anticoagulation guidance",
    ),
    InteractionRule(
        key="anticoag_nsaid",
        name="Anticoagulant with concurrent NSAID",
        severity="red",
        required_classes=(("anticoag",), ("nsaid",)),
        mechanism=(
            "NSAIDs impair platelet function and erode gastric mucosa, "
            "multiplying bleeding risk on top of anticoagulation."
        ),
        recommendation=(
            "Hold the NSAID; substitute acetaminophen; reassess "
            "anticoagulant indication and bleeding risk."
        ),
        citation="ACCP anticoagulation guidance",
    ),
    InteractionRule(
        key="dual_anticoagulation",
        name="Two concurrent anticoagulants",
        severity="red",
        required_classes=(("anticoag",), ("anticoag",)),
        mechanism=(
            "Two therapeutic anticoagulants compound bleeding risk without "
            "added efficacy unless a deliberate bridge is underway."
        ),
        recommendation=(
            "Verify intent (bridge vs duplication); discontinue one agent "
            "unless a documented bridging plan exists."
        ),
        citation="ACCP anticoagulation guidance",
    ),
    InteractionRule(
        key="hyperkalemia_k_retainers",
        name="Potassium-retaining agent with hyperkalemia",
        severity="red",
        required_classes=(("k_sparing", "ace_inhibitor", "arb"),),
        context_condition=ContextCondition(
            description="potassium >= 5.5", lab="potassium", lab_gte=5.5,
        ),
        mechanism=(
            "K-sparing diuretics and RAAS inhibitors blunt potassium "
            "excretion and will worsen existing hyperkalemia."
        ),
        recommendation=(
            "Hold potassium-retaining agents (ACEi/ARB, K-sparing "
            "diuretic); recheck potassium and obtain an ECG."
        ),
        citation="KDIGO / hyperkalemia management consensus",
    ),
    InteractionRule(
        key="doac_antiplatelet",
        name="DOAC with antiplatelet dual therapy",
        severity="amber",
        required_classes=(("anticoagulant_doac",), ("antiplatelet",)),
        mechanism=(
            "Combining a DOAC with antiplatelet therapy roughly doubles "
            "major bleeding risk versus anticoagulation alone."
        ),
        recommendation=(
            "Confirm the indication for combined antithrombotic therapy; "
            "drop the antiplatelet if not mandated by recent stent or ACS."
        ),
        citation="AUGUSTUS trial / ACC consensus on combined antithrombotic therapy",
    ),
    InteractionRule(
        key="triple_whammy",
        name="Triple whammy (ACEi/ARB + diuretic + NSAID)",
        severity="amber",
        required_classes=(("ace_inhibitor", "arb"), ("diuretic",), ("nsaid",)),
        mechanism=(
            "RAAS blockade, volume depletion, and prostaglandin inhibition "
            "together collapse glomerular perfusion and precipitate AKI."
        ),
        recommendation=(
            "Stop the NSAID; reassess diuretic dosing and renal function "
            "before continuing the ACEi/ARB."
        ),
        citation="Triple-whammy nephrotoxicity literature (Lapi et al., BMJ 2013)",
    ),
    InteractionRule(
        key="opioid_benzo_stack",
        name="Opioid + benzodiazepine sedation stack",
        severity="amber",
        required_classes=(("opioid",), ("benzodiazepine",)),
        mechanism=(
            "Opioids and benzodiazepines synergistically depress "
            "respiratory drive and level of consciousness."
        ),
        recommendation=(
            "Reduce or stage doses; add sedation monitoring and keep "
            "naloxone available."
        ),
        citation="FDA boxed warning on opioid-benzodiazepine co-prescribing; Beers Criteria 2023",
    ),
    InteractionRule(
        key="serotonergic_stack",
        name="Serotonergic medication stack",
        severity="amber",
        required_classes=(
            ("ssri", "snri", "serotonergic", "maoi"),
            ("ssri", "snri", "serotonergic", "maoi"),
        ),
        mechanism=(
            "Concurrent serotonergic agents have additive serotonin burden "
            "and can precipitate serotonin syndrome."
        ),
        recommendation=(
            "Deprescribe or substitute one serotonergic agent; monitor for "
            "clonus, hyperthermia, and agitation."
        ),
        citation="Boyer & Shannon, NEJM 2005 (serotonin syndrome)",
    ),
    InteractionRule(
        key="insulin_hypoglycemia",
        name="Insulin with documented hypoglycemia",
        severity="amber",
        required_classes=(("insulin",),),
        context_condition=ContextCondition(
            description="glucose <= 70", lab="glucose", lab_lte=70,
        ),
        mechanism=(
            "An insulin regimen that has already produced hypoglycemia "
            "signals a dose/monitoring mismatch; continuing unchanged risks "
            "recurrent severe hypoglycemia."
        ),
        recommendation=(
            "Review insulin doses against intake and renal function; "
            "confirm scheduled POC glucose monitoring before further dosing."
        ),
        citation="ISMP List of High-Alert Medications (insulin); ADA inpatient glycemic guidance",
    ),
    InteractionRule(
        key="warfarin_supratherapeutic_inr",
        name="Warfarin with supratherapeutic INR",
        severity="amber",
        required_classes=(("vka",),),
        context_condition=ContextCondition(
            description="INR >= 4", lab="INR", lab_gte=4.0,
        ),
        mechanism=(
            "An INR above 4 on a vitamin K antagonist sharply increases "
            "major bleeding risk, usually from a drug interaction or dosing "
            "error."
        ),
        recommendation=(
            "Hold warfarin and review for interacting drugs; recheck INR "
            "and assess for bleeding / vitamin K per protocol."
        ),
        citation="ACCP/CHEST antithrombotic guidelines (VKA management)",
    ),
)


def _scan_supplemental(note: str) -> List[Finding]:
    out: List[Finding] = []
    lower = note.lower()
    for med, klass in SUPPLEMENTAL_MEDICATIONS.items():
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


def _active_meds(ext: ExtractionResult, note: str) -> Dict[str, Finding]:
    """Deduplicated map of canonical drug name -> first supporting finding.
    Skips negated findings; canonicalizes brand names."""
    meds: Dict[str, Finding] = {}
    for f in list(ext.meds) + _scan_supplemental(note):
        if f.metadata.get("negated"):
            continue
        canonical = ALIASES.get(f.label, f.label)
        meds.setdefault(canonical, f)
    return meds


def _assign_distinct(
    groups: Tuple[Tuple[str, ...], ...],
    meds: Dict[str, Finding],
) -> Optional[List[Tuple[str, Finding]]]:
    """Backtracking assignment of DISTINCT meds to class groups."""

    def _matches(finding: Finding, group: Tuple[str, ...]) -> bool:
        klass = finding.metadata.get("class", "")
        return any(sub in klass for sub in group)

    def _recurse(i: int, used: frozenset) -> Optional[List[Tuple[str, Finding]]]:
        if i == len(groups):
            return []
        for name, finding in meds.items():
            if name in used or not _matches(finding, groups[i]):
                continue
            rest = _recurse(i + 1, used | {name})
            if rest is not None:
                return [(name, finding)] + rest
        return None

    return _recurse(0, frozenset())


def _context_satisfied(
    cond: Optional[ContextCondition], ext: ExtractionResult
) -> Tuple[bool, List[Span]]:
    if cond is None:
        return True, []
    evidence: List[Span] = []
    if cond.lab and (cond.lab_gte is not None or cond.lab_lte is not None):
        for lab in ext.labs:
            if lab.metadata.get("negated") or lab.label != cond.lab or not lab.value:
                continue
            try:
                value = float(lab.value)
            except ValueError:
                continue
            if cond.lab_gte is not None and value >= cond.lab_gte:
                evidence.append(lab.evidence)
                break
            if cond.lab_lte is not None and value <= cond.lab_lte:
                evidence.append(lab.evidence)
                break
    if cond.symptom:
        for sym in ext.symptoms:
            if sym.metadata.get("negated"):
                continue
            if sym.label == cond.symptom:
                evidence.append(sym.evidence)
                break
    return bool(evidence), evidence


def screen_interactions(ext: ExtractionResult, note: str) -> List[InteractionFlag]:
    """Run the full rule table against one note's extraction; flags sorted
    red-first, then rule-table order."""
    meds = _active_meds(ext, note)
    flagged: List[Tuple[int, int, InteractionFlag]] = []
    for idx, rule in enumerate(INTERACTION_RULES):
        assignment = _assign_distinct(rule.required_classes, meds)
        if assignment is None:
            continue
        satisfied, context_evidence = _context_satisfied(rule.context_condition, ext)
        if not satisfied:
            continue
        flag = InteractionFlag(
            rule_key=rule.key,
            name=rule.name,
            severity=rule.severity,
            mechanism=rule.mechanism,
            recommendation=rule.recommendation,
            citation=rule.citation,
            meds_involved=[
                MedInvolved(
                    name=name,
                    drug_class=finding.metadata.get("class", ""),
                    evidence=finding.evidence,
                )
                for name, finding in assignment
            ],
            context_evidence=context_evidence,
        )
        flagged.append((SEVERITY_RANK.get(rule.severity, 9), idx, flag))

    flagged.sort(key=lambda item: (item[0], item[1]))
    return [flag for _, _, flag in flagged]


# ===========================================================================
# SECTION 5 — Cascading bottleneck classifier
# FROZEN COPY of app/services/bottleneck.py — see test_aip_logic_parity.py
# ===========================================================================

BOTTLENECK_LABELS: Dict[str, str] = {
    "missing_soc": "Missing standard-of-care step",
    "med_risk": "Medication safety risk",
    "awaiting_consult": "Awaiting specialist consult",
    "awaiting_imaging": "Awaiting imaging",
    "dispo_delay": "Discharge / placement delay",
    "readmit_risk": "High readmission risk",
    "clear": "No active bottleneck",
}

URGENCY_RANK = {"red": 0, "amber": 1, "green": 2}


@dataclass
class Bottleneck:
    category: str
    label: str
    urgency: str                  # red | amber | green
    owner: str                    # physician | nurse | pharmacist | case_manager | social_worker
    recommended_action: str
    rationale: str
    evidence: List[Span] = field(default_factory=list)
    citation: Optional[str] = None
    protocol_key: Optional[str] = None   # set when rooted in a protocol gap


def _missing_soc(note: str, ext: ExtractionResult, sfs: List[SilentFailure]) -> Optional[Bottleneck]:
    if not sfs:
        return None
    # Take the highest-urgency miss (stable sort preserves protocol order).
    sfs_sorted = sorted(sfs, key=lambda s: URGENCY_RANK[s.urgency])
    sf = sfs_sorted[0]
    others = [s.missing_action for s in sfs_sorted[1:] if s.protocol_key == sf.protocol_key]
    extra = f" Additional gaps: {', '.join(others)}." if others else ""

    return Bottleneck(
        category="missing_soc",
        label=BOTTLENECK_LABELS["missing_soc"],
        urgency=sf.urgency,
        owner=sf.owner,
        recommended_action=sf.missing_action,
        rationale=(
            f"{sf.protocol_name} triggered by note evidence "
            f"“{sf.trigger_evidence.text}” but the required step "
            f"“{sf.missing_action}” is not documented.{extra}"
        ),
        evidence=[sf.trigger_evidence],
        citation=sf.citation,
        protocol_key=sf.protocol_key,
    )


# Interaction flags that duplicate a triggered protocol's own missing
# medication-review step are folded INTO that protocol gap rather than
# surfacing as a second, competing bottleneck. Policy (clinician-facing):
# when the protocol already owes a medication review (e.g. the AKI workup's
# "Medication review for nephrotoxins"), the nephrotoxin flag is the evidence
# FOR that gap — route once, to the protocol owner, instead of splitting the
# same problem across physician and pharmacist queues.
_FLAG_SUBSUMED_BY_PROTOCOL_GAP: Dict[str, tuple] = {
    "nephrotoxic_combo_aki": ("aki", "med_review"),
}


def _flag_subsumed(flag: InteractionFlag, pms: List[ProtocolMatch]) -> bool:
    target = _FLAG_SUBSUMED_BY_PROTOCOL_GAP.get(flag.rule_key)
    if not target:
        return False
    proto_key, action_key = target
    return any(
        pm.triggered
        and pm.protocol.key == proto_key
        and any(a.key == action_key for a in pm.missing)
        for pm in pms
    )


def _med_risk(
    note: str, ext: ExtractionResult, flags: Optional[List[InteractionFlag]] = None
) -> Optional[Bottleneck]:
    """Promote the highest-severity interaction flag to a med_risk
    bottleneck. Operational signal for the pharmacist queue, not a clinical
    decision aid."""
    if flags is None:
        flags = screen_interactions(ext, note)
    if not flags:
        return None
    top = flags[0]
    med_list = ", ".join(sorted({m.name for m in top.meds_involved}))
    evidence_spans = [m.evidence for m in top.meds_involved[:3]] + top.context_evidence[:2]
    return Bottleneck(
        category="med_risk",
        label=BOTTLENECK_LABELS["med_risk"],
        urgency=top.severity,
        owner="pharmacist",
        recommended_action=f"Pharmacy review: {top.recommendation}",
        rationale=(
            f"{top.name}: {top.mechanism} Medications involved: {med_list}."
        ),
        evidence=evidence_spans,
        citation=top.citation,
    )


def _awaiting_consult(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    pending = [c for c in ext.consults if c.value == "pending"]
    if not pending:
        return None
    services = sorted({c.label.replace("_", " ") for c in pending})
    spans = [c.evidence for c in pending[:3]]
    return Bottleneck(
        category="awaiting_consult",
        label=BOTTLENECK_LABELS["awaiting_consult"],
        urgency="amber",
        owner="physician",
        recommended_action=(
            f"Page {services[0]} attending; if no callback in 30 min, "
            "escalate to chief on call."
        ),
        rationale=(
            f"Consult to {', '.join(services)} is documented as pending with "
            "no note in the chart. Patient otherwise medically optimized."
        ),
        evidence=spans,
    )


def _awaiting_imaging(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    pending = [i for i in ext.imaging if i.value == "pending"]
    if not pending:
        return None
    studies = sorted({i.label.upper() for i in pending})
    spans = [i.evidence for i in pending[:2]]
    return Bottleneck(
        category="awaiting_imaging",
        label=BOTTLENECK_LABELS["awaiting_imaging"],
        urgency="amber",
        # NOTE: the shipped corpus labels awaiting_imaging rows with
        # expected_owner=physician, but the canonical routing table encodes
        # "nurse". We keep the canonical "nurse" routing and flag the
        # corpus/spec mismatch for the data owners (see eval docs) rather
        # than special-casing notes.
        owner="nurse",
        recommended_action=(
            f"Call radiology to expedite {studies[0]}; confirm patient is "
            "ready (NPO, IV access, contrast eligibility)."
        ),
        rationale=(
            f"{', '.join(studies)} ordered but not yet resulted; downstream "
            "disposition depends on this study."
        ),
        evidence=spans,
    )


def _dispo_delay(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    blockers = [d for d in ext.dispo if d.label != "medically_ready"]
    if not blockers:
        return None
    primary = blockers[0]
    pretty = {
        "snf_placement": "SNF placement",
        "home_oxygen": "home oxygen setup",
        "insurance_auth": "insurance authorization",
        "dme_delay": "DME / equipment delivery",
        "pt_clearance": "physical therapy clearance",
        "social_placement": "social / placement support",
        "training_incomplete": "patient or family training",
        "case_mgmt_pending": "case management follow-up",
    }.get(primary.label, primary.label.replace("_", " "))

    return Bottleneck(
        category="dispo_delay",
        label=BOTTLENECK_LABELS["dispo_delay"],
        urgency="green",
        owner="case_manager",
        recommended_action=(
            f"Case management: own {pretty}; daily 3PM huddle update on this "
            "patient until resolved."
        ),
        rationale=(
            f"Patient appears medically ready but discharge is held by {pretty}."
        ),
        evidence=[b.evidence for b in blockers[:3]],
    )


def _readmit_risk(note: str, ext: ExtractionResult) -> Optional[Bottleneck]:
    if not ext.risk_factors:
        return None
    return Bottleneck(
        category="readmit_risk",
        label=BOTTLENECK_LABELS["readmit_risk"],
        urgency="amber",
        owner="case_manager",
        recommended_action=(
            "Schedule transitional-care visit within 7 days; arrange "
            "medication reconciliation and home-health referral before "
            "discharge."
        ),
        rationale=(
            "Multiple readmission-risk markers in the note: prior recent "
            "admissions, adherence concerns, or limited support."
        ),
        evidence=[r.evidence for r in ext.risk_factors[:3]],
    )


CASCADE = [
    ("missing_soc", _missing_soc),       # most dangerous — bundle missing
    ("med_risk",    _med_risk),          # patient-safety
    ("awaiting_consult", _awaiting_consult),
    ("awaiting_imaging", _awaiting_imaging),
    ("readmit_risk", _readmit_risk),     # before dispo: addressable upstream
    ("dispo_delay", _dispo_delay),
]


def _classify(note: str, ext: ExtractionResult) -> List[Bottleneck]:
    """Full cascade. Returns bottlenecks sorted primary-first; element [0]
    is what materializes as the Bottleneck object."""
    pms = evaluate_protocols(note)
    sfs = silent_failures(note, matches=pms)

    # Screen interactions once; drop flags subsumed by a triggered protocol's
    # own missing medication-review step (see _FLAG_SUBSUMED_BY_PROTOCOL_GAP).
    flags = [
        f for f in screen_interactions(ext, note) if not _flag_subsumed(f, pms)
    ]

    bottlenecks: List[Bottleneck] = []
    for key, fn in CASCADE:
        if key == "missing_soc":
            b = fn(note, ext, sfs)
        elif key == "med_risk":
            b = fn(note, ext, flags)
        else:
            b = fn(note, ext)
        if b:
            bottlenecks.append(b)

    if not bottlenecks:
        return [
            Bottleneck(
                category="clear",
                label=BOTTLENECK_LABELS["clear"],
                urgency="green",
                owner="",
                recommended_action="No action required; consider for discharge.",
                rationale="No active operational, safety, or protocol gaps detected.",
                evidence=[],
            )
        ]

    # Sort by urgency (red < amber < green) then by cascade order.
    #
    # Equal-urgency tie-break policy (clinician-reviewed): a protocol gap
    # (missing_soc — an undone bundle step) normally outranks a medication
    # flag of the same urgency, per cascade order. EXCEPTION: a red
    # interaction flag carrying objective context evidence — harm in
    # progress, such as an anticoagulant with documented melena — outranks
    # an equal-urgency protocol gap, because stopping active harm precedes
    # completing bundle documentation and routes to a pharmacist who can act
    # in parallel. Flags that merely duplicate a protocol's own missing
    # med-review step never reach this comparison (subsumed above).
    cascade_order: Dict[str, float] = {k: float(i) for i, (k, _) in enumerate(CASCADE)}
    if flags and flags[0].severity == "red" and flags[0].context_evidence:
        cascade_order["med_risk"] = cascade_order["missing_soc"] - 0.5
    bottlenecks.sort(key=lambda b: (URGENCY_RANK[b.urgency], cascade_order[b.category]))
    return bottlenecks


# ===========================================================================
# SECTION 6 — Public entry point (the Foundry Function body)
# ===========================================================================

def classify_bottleneck(note_text: str, age: int) -> dict:
    """Classify one patient note into its primary operational bottleneck.

    Inputs
        note_text : the linked Note object's `note_text` property.
        age       : the bound Patient's `age` property (currently unused by
                    the rule cascade; see module docstring).

    Returns a dict that maps onto the `Bottleneck` object type
    (01_ontology_spec.md) plus the two Workshop display properties:

        category            one of: missing_soc | med_risk | awaiting_consult
                            | awaiting_imaging | readmit_risk | dispo_delay
                            | clear
        urgency             red | amber | green
        owner               physician | nurse | pharmacist | case_manager
                            | "" (clear)
        protocol_key        FK -> Protocol when rooted in a protocol gap,
                            else None
        evidence_span       literal substring of the note that fired the rule
        summary             human-readable rationale ("why is this patient
                            stuck?")
        recommended_action  imperative coordination step (NOT a clinical
                            order)
        citation            the published bundle / rule source, or None

    Deterministic: no model call, no randomness, no clock. Safe to re-run
    on a schedule (05_automations_spec.md) — same note always re-materializes
    the same Bottleneck.
    """
    ext = extract(note_text)
    primary = _classify(note_text, ext)[0]
    return {
        "category": primary.category,
        "urgency": primary.urgency,
        "owner": primary.owner,
        "protocol_key": primary.protocol_key,
        "evidence_span": primary.evidence[0].text if primary.evidence else "",
        "summary": primary.rationale,
        "recommended_action": primary.recommended_action,
        "citation": primary.citation,
    }


if __name__ == "__main__":
    # Smoke check: runs on a minimal notional note, prints the writeback dict.
    demo = (
        "HPI: 81yo female on apixaban for AFib presents with melena x 2 days. "
        "Labs: hgb 8.4, INR 1.0. Assessment: upper GI bleed on DOAC. "
        "Plan: GI consult."
    )
    import json as _json
    print(_json.dumps(classify_bottleneck(demo, 81), indent=2))
