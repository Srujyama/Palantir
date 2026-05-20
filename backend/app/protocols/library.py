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
                r"hold\s+(NSAID|ibuprofen|naproxen|ACE|ARB|lisinopril|losartan)",
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
                r"\bdialysis\b", r"\bCRRT\b", r"\bHD\b",
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


def by_key(key: str) -> Protocol | None:
    for p in PROTOCOLS:
        if p.key == key:
            return p
    return None
