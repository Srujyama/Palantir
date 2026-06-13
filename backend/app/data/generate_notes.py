"""
Generates a notional patient note dataset for the Bottleneck Radar demo.

Notes are synthetic but written in realistic clinical-note voice (HPI / PMH /
exam / labs / imaging / assessment / plan). Each note is seeded with one or
more bottleneck signals so the downstream extraction and classification
pipeline has something honest to find.

NOT real patient data. Generated locally, never persisted to any external
service. Names are obviously synthetic ("Patient A", "Patient B", ...).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import List


SEED = 7
random.seed(SEED)

OUT_PATH = Path(__file__).parent / "patient_notes.json"


# ---------------------------------------------------------------------------
# Templates. Each template encodes a bottleneck pattern. The note text is
# written so a downstream extractor can find the signals; the `truth` field
# carries the ground-truth bottleneck label for evaluation.
# ---------------------------------------------------------------------------

@dataclass
class PriorNote:
    """An earlier note for the same patient — clinical history only.

    Priors narrate trajectory (lactate clearing, creatinine worsening); they
    are NEVER read by the classifier or the eval, which see only `note` /
    `note_text`. hours_ago is the offset behind the current note.
    """
    hours_ago: int
    note_text: str


@dataclass
class Template:
    name: str
    chief_complaint: str
    note: str
    icd10_hints: List[str]
    truth_bottleneck: str          # awaiting_consult | awaiting_imaging |
                                   # dispo_delay | missing_soc | med_risk |
                                   # readmit_risk | clear
    truth_protocol: str = ""       # e.g. "sepsis", "acs", "" if none expected
    expected_owner: str = ""       # physician | nurse | pharmacist | case_manager | social_worker
    prior_notes: List[PriorNote] = field(default_factory=list)  # history; not classified


TEMPLATES: List[Template] = [
    # -------- Sepsis: silent failure (no antibiotics documented) -----------
    Template(
        name="sepsis_no_abx",
        chief_complaint="Fever, hypotension, altered mental status",
        note=(
            "HPI: 72yo presenting from SNF with fever to 39.4C, BP 88/52, HR 122, RR 24, "
            "SpO2 91% on room air. Family reports two days of decreased PO intake and confusion. "
            "PMH: HTN, DM2, recurrent UTI.\n"
            "Exam: ill-appearing, dry mucous membranes, no focal infection on skin exam. "
            "Lung exam clear. Mild suprapubic tenderness.\n"
            "Labs: WBC 18.2, lactate 3.1, creatinine 1.9 (baseline 1.0), UA cloudy with "
            "many bacteria and 50+ WBC/hpf. Blood cultures drawn.\n"
            "Imaging: CXR no infiltrate.\n"
            "Assessment: severe sepsis, urinary source. Meets SIRS criteria with end-organ dysfunction.\n"
            "Plan: IV fluids 30 mL/kg bolus initiated. Will trend lactate. Admit to medicine."
        ),
        icd10_hints=["A41.9", "N39.0", "R65.20"],
        truth_bottleneck="missing_soc",
        truth_protocol="sepsis",
        expected_owner="physician",
        prior_notes=[
            PriorNote(
                hours_ago=6,
                note_text=(
                    "HPI: 72yo from SNF, febrile to 38.9C, BP 94/58, HR 110. Decreased PO intake.\n"
                    "Labs: WBC 16.4, lactate 4.1, creatinine 1.4. UA pending.\n"
                    "Assessment: presumed sepsis, source unclear.\n"
                    "Plan: cultures pending, fluids started, recheck labs."
                ),
            ),
            PriorNote(
                hours_ago=3,
                note_text=(
                    "Interval: febrile 39.2C, BP 90/55, HR 116.\n"
                    "Labs: WBC 17.6, lactate 3.6, creatinine 1.7. UA cloudy, bacteria present.\n"
                    "Assessment: severe sepsis, likely urinary source.\n"
                    "Plan: continue resuscitation, trend lactate."
                ),
            ),
        ],
    ),
    # -------- ACS: silent failure (troponin elevated, no cardio consult) ---
    Template(
        name="acs_no_consult",
        chief_complaint="Substernal chest pressure",
        note=(
            "HPI: 64yo male, smoker, with 2 hours of substernal chest pressure radiating to left arm, "
            "associated diaphoresis and nausea. No prior cardiac history. Symptoms ongoing in ED.\n"
            "Exam: diaphoretic, BP 148/92, HR 96, lungs clear, no JVD, no edema.\n"
            "ECG: ST depression V4-V6, T-wave inversion lateral leads.\n"
            "Labs: troponin I 0.42 (ref <0.04), repeat at 3h pending. CK-MB elevated.\n"
            "Assessment: NSTEMI, intermediate-to-high risk.\n"
            "Plan: ASA 325 given. Admit to telemetry. Will discuss with hospitalist."
        ),
        icd10_hints=["I21.4", "I20.0"],
        truth_bottleneck="missing_soc",
        truth_protocol="acs",
        expected_owner="physician",
    ),
    # -------- Stroke: time-window sensitive ---------------------------------
    Template(
        name="stroke_no_neuro",
        chief_complaint="Acute right-sided weakness",
        note=(
            "HPI: 78yo female, last known well 90 minutes ago. Husband witnessed acute onset "
            "right hemiparesis and expressive aphasia at breakfast.\n"
            "Exam: NIHSS 14. Right facial droop, right arm 1/5, right leg 2/5. Aphasic.\n"
            "Vitals: BP 192/104, HR 78, glucose 142.\n"
            "Imaging: head CT non-contrast pending.\n"
            "Assessment: acute ischemic stroke, within tPA window.\n"
            "Plan: BP control, monitor in ED."
        ),
        icd10_hints=["I63.9", "G81.91"],
        truth_bottleneck="missing_soc",
        truth_protocol="stroke",
        expected_owner="physician",
    ),
    # -------- Awaiting consult: ortho ---------------------------------------
    Template(
        name="hip_fx_awaiting_ortho",
        chief_complaint="Post-fall left hip pain, unable to bear weight",
        note=(
            "HPI: 81yo female, mechanical fall from standing at home. Severe left hip pain, "
            "unable to bear weight. No head strike, no LOC.\n"
            "Exam: left leg shortened and externally rotated. Distal pulses intact. Sensation intact.\n"
            "Imaging: pelvis XR confirms left intertrochanteric fracture.\n"
            "Labs: hgb 10.8, INR 1.1, basic metabolic unremarkable.\n"
            "Assessment: left intertrochanteric hip fracture, surgical candidate.\n"
            "Plan: NPO. Pain control. Orthopedic consult requested 14h ago, awaiting callback. "
            "Patient otherwise medically optimized for OR."
        ),
        icd10_hints=["S72.141A"],
        truth_bottleneck="awaiting_consult",
        expected_owner="physician",
    ),
    # -------- Awaiting consult: nephrology, AKI -----------------------------
    Template(
        name="aki_awaiting_renal",
        chief_complaint="Decreased urine output, rising creatinine",
        note=(
            "HPI: 69yo male admitted 3 days ago for community-acquired pneumonia, now with "
            "creatinine rising from 1.1 to 3.4 over 48h. UOP <300 mL/24h.\n"
            "Exam: euvolemic, no edema, lungs improving.\n"
            "Labs: K 5.8, BUN 62, FENa 0.4%, urine sediment with muddy brown casts.\n"
            "Imaging: renal US no hydronephrosis.\n"
            "Assessment: AKI, likely ATN vs prerenal. Vancomycin trough 28.\n"
            "Plan: held vancomycin. Nephrology consult placed yesterday morning, no note in chart."
        ),
        icd10_hints=["N17.9", "T36.91XA"],
        truth_bottleneck="awaiting_consult",
        expected_owner="physician",
        prior_notes=[
            PriorNote(
                hours_ago=48,
                note_text=(
                    "HD1 for CAP. Labs: creatinine 1.1, K 4.2. UOP adequate.\n"
                    "Plan: ceftriaxone + azithromycin, IV fluids."
                ),
            ),
            PriorNote(
                hours_ago=24,
                note_text=(
                    "HD2. Creatinine 2.2, K 5.1. UOP declining to 600 mL/24h. Vancomycin trough 22.\n"
                    "Assessment: developing AKI.\n"
                    "Plan: monitor renal function, recheck vanc trough."
                ),
            ),
        ],
    ),
    # -------- Awaiting imaging: CT abd --------------------------------------
    Template(
        name="rlq_pain_awaiting_ct",
        chief_complaint="Right lower quadrant pain",
        note=(
            "HPI: 28yo female, 18 hours of progressive RLQ pain, anorexia, low-grade fever 38.1.\n"
            "Exam: RLQ tenderness with rebound, positive Rovsing.\n"
            "Labs: WBC 14.1, beta-hCG negative, lipase normal.\n"
            "Imaging: CT abd/pelvis with contrast ordered 5h ago, still in queue per radiology. "
            "US RLQ inconclusive.\n"
            "Assessment: clinical suspicion for acute appendicitis pending imaging.\n"
            "Plan: NPO, IV fluids, surgery aware. Awaiting CT for definitive disposition."
        ),
        icd10_hints=["K35.80", "R10.31"],
        truth_bottleneck="awaiting_imaging",
        expected_owner="physician",
    ),
    # -------- Awaiting imaging: MRI brain -----------------------------------
    Template(
        name="seizure_awaiting_mri",
        chief_complaint="First-time seizure",
        note=(
            "HPI: 41yo male, witnessed generalized tonic-clonic seizure x2 minutes at work. "
            "Postictal x 30 min, now at baseline. No prior seizure history.\n"
            "Exam: nonfocal neuro exam, tongue laceration on left lateral.\n"
            "Labs: glucose 96, sodium 138, alcohol negative, tox screen pending.\n"
            "Imaging: head CT no acute findings. MRI brain ordered, scheduled for tomorrow AM.\n"
            "Assessment: new-onset seizure, etiology undetermined.\n"
            "Plan: admit for observation, MRI in AM, neurology to see post-MRI."
        ),
        icd10_hints=["R56.9", "G40.909"],
        truth_bottleneck="awaiting_imaging",
        expected_owner="physician",
    ),
    # -------- Discharge placement delay: SNF -------------------------------
    Template(
        name="copd_dispo_snf",
        chief_complaint="COPD exacerbation, now resolved",
        note=(
            "HPI: 74yo male, day 5 of admission for COPD exacerbation. Off supplemental O2 x 24h, "
            "ambulating with assistance, tolerating PO. Medically ready for discharge per primary team.\n"
            "Exam: lungs with mild expiratory wheeze, no distress.\n"
            "Assessment: COPD exacerbation, resolved. Deconditioned.\n"
            "Plan: SNF placement requested 3 days ago. Case management notes 4 SNFs declined "
            "due to no insurance authorization. Patient unable to safely return home alone."
        ),
        icd10_hints=["J44.1", "Z74.09"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Discharge placement delay: home oxygen ------------------------
    Template(
        name="chf_dispo_o2",
        chief_complaint="CHF exacerbation, awaiting home O2 setup",
        note=(
            "HPI: 68yo female, admitted for acute decompensated heart failure. Diuresed 6L over 4 days, "
            "now euvolemic. Walks 100 feet with rolling walker, SpO2 88% on room air with ambulation, "
            "94% on 2L NC.\n"
            "Exam: lungs clear, no edema, JVP normal.\n"
            "Assessment: HFpEF, optimized. Requires home oxygen.\n"
            "Plan: home O2 ordered 36h ago, DME vendor backlogged. "
            "Family training on equipment not yet completed. Case management following."
        ),
        icd10_hints=["I50.32", "Z99.81"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Med risk: nephrotoxic + AKI -----------------------------------
    Template(
        name="nephrotoxic_med",
        chief_complaint="Worsening renal function on home meds",
        note=(
            "HPI: 77yo male admitted with pneumonia, now 4 days in. Creatinine has risen "
            "from 1.0 to 1.7. Patient continues home lisinopril 40mg daily and ibuprofen "
            "800mg TID for chronic back pain. Started on IV contrast CT yesterday. "
            "Vancomycin and tobramycin per infectious disease.\n"
            "Exam: stable, lungs improving.\n"
            "Labs: Cr 1.7, K 5.1, BUN 38.\n"
            "Assessment: developing AKI, likely multifactorial.\n"
            "Plan: continue current antibiotics, monitor renal function."
        ),
        icd10_hints=["N17.9", "T39.395A"],
        truth_bottleneck="med_risk",
        expected_owner="pharmacist",
    ),
    # -------- Med risk: anticoagulant + bleed risk --------------------------
    Template(
        name="anticoag_bleed_risk",
        chief_complaint="GIB on apixaban",
        note=(
            "HPI: 81yo female on apixaban 5mg BID for AFib presents with melena x 2 days, "
            "hgb dropped from baseline 12 to 8.4. Also on aspirin 81mg and ibuprofen PRN.\n"
            "Exam: pale, tachycardic to 108, BP 102/64.\n"
            "Labs: hgb 8.4, plt 198, INR 1.0, anti-Xa pending.\n"
            "Assessment: upper GI bleed on dual antiplatelet plus DOAC.\n"
            "Plan: hold apixaban, hold aspirin, GI consult. Continue ibuprofen for arthritis pain."
        ),
        icd10_hints=["K92.2", "I48.91", "D62"],
        truth_bottleneck="med_risk",
        expected_owner="pharmacist",
    ),
    # -------- Readmission risk: poor follow-up plan ------------------------
    Template(
        name="dm_readmit_risk",
        chief_complaint="DKA, third admission this year",
        note=(
            "HPI: 34yo female with type 1 DM, third DKA admission in 8 months. Reports running out "
            "of insulin again, no PCP follow-up since last discharge. Lives alone, no family support, "
            "intermittent housing.\n"
            "Exam: improved, anion gap closed.\n"
            "Labs: glucose 142, gap 8, bicarbonate 22.\n"
            "Assessment: DKA resolved. High risk for early readmission given social factors and "
            "medication non-adherence pattern.\n"
            "Plan: standard DM follow-up. No outpatient endocrinology arranged."
        ),
        icd10_hints=["E10.10", "Z91.120"],
        truth_bottleneck="readmit_risk",
        expected_owner="case_manager",
    ),
    # -------- Readmission risk: CHF, no scale at home ----------------------
    Template(
        name="chf_readmit_risk",
        chief_complaint="CHF readmission within 14 days",
        note=(
            "HPI: 70yo male, second CHF admission in 14 days. Reports unable to weigh self at home "
            "(no scale), unsure of fluid restriction, taking furosemide 'when I feel puffy.' "
            "Lives with elderly spouse, no home health.\n"
            "Exam: 2+ lower extremity edema, lungs with bibasilar crackles.\n"
            "Labs: BNP 1840, Cr 1.4.\n"
            "Assessment: ADHF, recurrent. Knowledge and adherence gaps.\n"
            "Plan: diurese, optimize GDMT, plan discharge to home."
        ),
        icd10_hints=["I50.32"],
        truth_bottleneck="readmit_risk",
        expected_owner="case_manager",
    ),
    # -------- Pneumonia: silent failure (no antibiotics within 6h) ---------
    Template(
        name="cap_late_abx",
        chief_complaint="Cough, fever, hypoxia",
        note=(
            "HPI: 58yo female, 3 days of productive cough, fever to 38.7, dyspnea on exertion. "
            "Arrived to ED 7 hours ago.\n"
            "Exam: RR 22, SpO2 92% RA, right basilar crackles.\n"
            "Labs: WBC 14.8, lactate 1.6, procalcitonin 2.1.\n"
            "Imaging: CXR with right lower lobe consolidation.\n"
            "Assessment: community-acquired pneumonia, CURB-65 = 1.\n"
            "Plan: admit to medicine. IV fluids running. Antibiotic selection to be determined on the floor."
        ),
        icd10_hints=["J18.9"],
        truth_bottleneck="missing_soc",
        truth_protocol="cap",
        expected_owner="physician",
    ),
    # -------- DKA: missing insulin drip ------------------------------------
    Template(
        name="dka_no_drip",
        chief_complaint="Hyperglycemia, ketosis",
        note=(
            "HPI: 22yo male T1DM, presents with N/V, abdominal pain, glucose 512.\n"
            "Exam: kussmaul respirations, dry mucous membranes.\n"
            "Labs: glucose 512, bicarb 9, anion gap 24, beta-hydroxybutyrate 6.2, K 5.3, pH 7.18.\n"
            "Assessment: DKA, severe.\n"
            "Plan: IV fluids initiated. Repeat labs in 2h."
        ),
        icd10_hints=["E10.10"],
        truth_bottleneck="missing_soc",
        truth_protocol="dka",
        expected_owner="physician",
    ),
    # -------- Clear / no bottleneck (negative example) ---------------------
    Template(
        name="clear_uti",
        chief_complaint="Uncomplicated UTI, ready for discharge",
        note=(
            "HPI: 38yo female, 2 days of dysuria and urinary frequency, no fever, no flank pain.\n"
            "Exam: afebrile, no CVA tenderness, mild suprapubic discomfort.\n"
            "Labs: UA positive nitrites and leukocyte esterase, urine culture pending.\n"
            "Assessment: uncomplicated cystitis.\n"
            "Plan: nitrofurantoin 100mg BID x 5 days, follow up with PCP if symptoms persist. "
            "Discharge home."
        ),
        icd10_hints=["N30.00"],
        truth_bottleneck="clear",
        expected_owner="",
    ),
    Template(
        name="clear_migraine",
        chief_complaint="Migraine, treated and ready to leave",
        note=(
            "HPI: 32yo female with known migraine, presents with typical aura then severe HA, "
            "now resolved after IV fluids, ketorolac, and metoclopramide.\n"
            "Exam: nonfocal neuro, comfortable.\n"
            "Assessment: migraine, treated.\n"
            "Plan: discharge home with abortive medications, neurology follow-up scheduled."
        ),
        icd10_hints=["G43.909"],
        truth_bottleneck="clear",
        expected_owner="",
    ),
    # -------- Awaiting consult: psych hold ---------------------------------
    Template(
        name="psych_consult_delay",
        chief_complaint="Suicidal ideation, awaiting psychiatry",
        note=(
            "HPI: 26yo male brought in by police on 5150 hold for SI with plan. Calm and cooperative now.\n"
            "Exam: stable vitals, no acute medical issues.\n"
            "Assessment: acute SI, requires inpatient psychiatric evaluation.\n"
            "Plan: psychiatry consult requested 9 hours ago, no eval yet. Patient sitting in ED with sitter."
        ),
        icd10_hints=["R45.851"],
        truth_bottleneck="awaiting_consult",
        expected_owner="physician",
    ),
    # -------- Discharge: awaiting PT clearance -----------------------------
    Template(
        name="post_op_pt_clearance",
        chief_complaint="POD 2 from THA, awaiting PT clearance",
        note=(
            "HPI: 67yo female, post-op day 2 from elective right total hip arthroplasty. "
            "Pain controlled, tolerating diet, voiding spontaneously, hemoglobin stable.\n"
            "Exam: incision clean dry intact, no calf tenderness.\n"
            "Assessment: uncomplicated post-op course.\n"
            "Plan: medically ready for discharge home with home health. Awaiting PT to clear "
            "for stairs - eval requested yesterday, not yet seen."
        ),
        icd10_hints=["Z47.1"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Med risk: QT-prolonging combo --------------------------------
    Template(
        name="qt_prolong_combo",
        chief_complaint="Syncope on multiple QT-prolonging meds",
        note=(
            "HPI: 73yo female with witnessed syncope. Currently on amiodarone, citalopram 40mg, "
            "ondansetron PRN nausea, and started azithromycin 3 days ago for bronchitis.\n"
            "Exam: stable, no focal findings.\n"
            "Labs: K 3.4, Mg 1.6.\n"
            "ECG: QTc 540 ms (prior 460).\n"
            "Assessment: drug-induced QT prolongation, near-syncope concerning for TdP risk.\n"
            "Plan: telemetry, repeat ECG in AM."
        ),
        icd10_hints=["I49.8", "T50.905A"],
        truth_bottleneck="med_risk",
        expected_owner="pharmacist",
    ),
    # -------- PE: submassive, no risk stratification ------------------------
    Template(
        name="pe_no_risk_strat",
        chief_complaint="Pleuritic chest pain, dyspnea",
        note=(
            "HPI: 56yo male, post-op day 10 from L knee arthroplasty, now with sudden pleuritic chest pain "
            "and dyspnea. Saturating 90% on RA, improved to 96% on 2L NC.\n"
            "Exam: tachypneic, RR 28, HR 112. Lungs clear. Right calf swelling noted.\n"
            "Labs: D-dimer 4.8 (elevated).\n"
            "Imaging: CT-PA confirms bilateral segmental PE.\n"
            "Assessment: acute pulmonary embolism, hemodynamically stable.\n"
            "Plan: started on heparin drip. Admit to medicine."
        ),
        icd10_hints=["I26.99"],
        truth_bottleneck="missing_soc",
        truth_protocol="pe",
        expected_owner="physician",
    ),
    # -------- GI bleed: no PPI, no type/screen ------------------------------
    Template(
        name="gib_no_ppi",
        chief_complaint="Hematemesis x 2 episodes overnight",
        note=(
            "HPI: 62yo male with history of alcohol use disorder presenting with two episodes of "
            "frank hematemesis overnight, melena since this morning. Reports last drink yesterday evening.\n"
            "Exam: pale, BP 96/58, HR 108. Abdominal exam soft.\n"
            "Labs: hgb dropped to 7.2 from baseline 11.4, plt 142, INR 1.3.\n"
            "Assessment: upper GI bleed, likely variceal vs ulcer source.\n"
            "Plan: two large-bore IV access placed, IV fluids running. NPO. "
            "Will arrange GI consult in AM for endoscopy."
        ),
        icd10_hints=["K92.0", "K92.2"],
        truth_bottleneck="missing_soc",
        truth_protocol="gi_bleed",
        expected_owner="physician",
        prior_notes=[
            PriorNote(
                hours_ago=5,
                note_text=(
                    "HPI: 62yo male, one episode of hematemesis. BP 108/64, HR 96.\n"
                    "Labs: hgb 9.1, plt 150, INR 1.2.\n"
                    "Assessment: upper GI bleed.\n"
                    "Plan: IV access, type and screen sent, monitoring."
                ),
            ),
        ],
    ),
    # -------- AKI: no medication review -------------------------------------
    Template(
        name="aki_no_med_review",
        chief_complaint="Rising creatinine, oliguria",
        note=(
            "HPI: 71yo male admitted 4 days ago for cellulitis on vancomycin and tobramycin. "
            "Creatinine rising from baseline 1.0 to 2.4 over 36h. UOP <300 mL/24h. "
            "Home medications include lisinopril 40mg, naproxen 500mg BID, and recently "
            "received iodinated contrast for a CT angiogram.\n"
            "Exam: euvolemic.\n"
            "Labs: Cr 2.4, K 4.8, urine sediment with muddy brown casts. FENa 0.8%.\n"
            "Assessment: acute kidney injury, multifactorial.\n"
            "Plan: continue current regimen. Trend renal function."
        ),
        icd10_hints=["N17.9"],
        truth_bottleneck="missing_soc",
        truth_protocol="aki",
        expected_owner="physician",
    ),
    # -------- CIWA: alcohol withdrawal, no scoring documented ---------------
    Template(
        name="ciwa_no_scoring",
        chief_complaint="Alcohol withdrawal, tremulous",
        note=(
            "HPI: 48yo male with history of alcohol use disorder, last drink 18 hours ago. "
            "Presents with tremor, diaphoresis, anxiety. History of DTs in past admission.\n"
            "Exam: BP 168/96, HR 118, tremulous, mild diaphoresis. Oriented.\n"
            "Labs: AST 142, ALT 88, lipase 38.\n"
            "Assessment: alcohol withdrawal, moderate. AUD.\n"
            "Plan: thiamine 100mg IV given. Banana bag running. Admit to medicine."
        ),
        icd10_hints=["F10.230"],
        truth_bottleneck="missing_soc",
        truth_protocol="ciwa",
        expected_owner="physician",
    ),
    # -------- Neutropenic fever: late antibiotics ---------------------------
    Template(
        name="neutropenic_fever_late_abx",
        chief_complaint="Fever on chemotherapy, ANC 200",
        note=(
            "HPI: 54yo female with AML, day 9 of induction chemotherapy, presenting with fever to 38.6C. "
            "Reports mild fatigue, no localizing symptoms. Port-a-cath in place.\n"
            "Exam: well-appearing, no overt source. Port site without erythema.\n"
            "Labs: ANC 180, WBC 0.8, lactate 1.4. CXR clear.\n"
            "Assessment: neutropenic fever, no localizing source.\n"
            "Plan: blood cultures x2 drawn. Awaiting attending review before starting antibiotics."
        ),
        icd10_hints=["D70.9", "R50.9"],
        truth_bottleneck="missing_soc",
        truth_protocol="neutropenic_fever",
        expected_owner="physician",
    ),
    # -------- Hyperkalemia: severe, no ECG done -----------------------------
    Template(
        name="hyperk_no_ecg",
        chief_complaint="Severe hyperkalemia on routine labs",
        note=(
            "HPI: 66yo male with ESRD on hemodialysis, missed last HD session. "
            "Routine labs in clinic showed K 6.8.\n"
            "Exam: stable, no chest pain, no weakness.\n"
            "Labs: K 6.8, Cr 8.2, bicarb 16.\n"
            "Assessment: severe hyperkalemia, missed dialysis.\n"
            "Plan: arranging emergent HD. Calcium gluconate 1g IV given. "
            "Insulin 10 units IV with D50 administered."
        ),
        icd10_hints=["E87.5", "N18.6"],
        truth_bottleneck="missing_soc",
        truth_protocol="hyperkalemia",
        expected_owner="physician",
    ),
    # -------- COPD: no steroids documented ----------------------------------
    Template(
        name="copd_no_steroids",
        chief_complaint="COPD exacerbation, increased sputum",
        note=(
            "HPI: 69yo male with GOLD stage 3 COPD presents with 3 days of increased dyspnea, "
            "increased sputum production, sputum more purulent than baseline. Home O2 at 2L NC.\n"
            "Exam: in mild respiratory distress, expiratory wheeze throughout, RR 24, SpO2 86% on 2L NC.\n"
            "Labs: WBC 11.4, ABG pH 7.32 / PCO2 56 / PO2 64 on 2L NC.\n"
            "Imaging: CXR no infiltrate.\n"
            "Assessment: COPD exacerbation, moderate.\n"
            "Plan: DuoNeb nebulizer treatments. Azithromycin started. Admit to telemetry."
        ),
        icd10_hints=["J44.1"],
        truth_bottleneck="missing_soc",
        truth_protocol="copd",
        expected_owner="physician",
    ),
    # -------- Awaiting consult: GI bleed, GI not seen -----------------------
    Template(
        name="gib_awaiting_gi",
        chief_complaint="Slow GI bleed, awaiting endoscopy",
        note=(
            "HPI: 75yo female with chronic NSAID use presenting with melena x 4 days, "
            "now hemodynamically stable. Hgb 8.8 from baseline 11.2.\n"
            "Exam: stable, soft non-tender abdomen.\n"
            "Labs: hgb 8.8, plt 220, INR 1.1.\n"
            "Assessment: chronic GI blood loss, likely NSAID gastropathy.\n"
            "Plan: IV pantoprazole drip. Type and screen sent. NPO. "
            "GI consult placed 16h ago, awaiting callback for endoscopy scheduling."
        ),
        icd10_hints=["K92.1"],
        truth_bottleneck="awaiting_consult",
        expected_owner="physician",
    ),
    # -------- Awaiting consult: psych medical clearance ---------------------
    Template(
        name="psych_medical_clear",
        chief_complaint="Manic episode, on involuntary hold",
        note=(
            "HPI: 31yo male brought in by police on 5150 for grandiose delusions and "
            "agitation, history of bipolar I.\n"
            "Exam: agitated but cooperative now after IM olanzapine. Vitals stable.\n"
            "Labs: tox screen positive for amphetamines. Otherwise unremarkable.\n"
            "Assessment: acute mania.\n"
            "Plan: psychiatry consult placed yesterday, awaiting eval. Patient remains in ED "
            "with sitter, no inpatient psych bed identified."
        ),
        icd10_hints=["F31.2"],
        truth_bottleneck="awaiting_consult",
        expected_owner="physician",
    ),
    # -------- Awaiting imaging: V/Q scan PE workup --------------------------
    Template(
        name="pe_awaiting_vq",
        chief_complaint="Dyspnea, contrast contraindication",
        note=(
            "HPI: 44yo female, postpartum day 3 with dyspnea and pleuritic chest pain. "
            "Cr 1.6, breastfeeding, declined CT-PA.\n"
            "Exam: RR 20, SpO2 95% RA, HR 102.\n"
            "Labs: D-dimer 3.2.\n"
            "Imaging: V/Q scan ordered yesterday, scheduled for today PM. "
            "Lower extremity dopplers negative.\n"
            "Assessment: workup for PE.\n"
            "Plan: empiric heparin drip while awaiting study."
        ),
        icd10_hints=["R06.02", "O88.211"],
        truth_bottleneck="awaiting_imaging",
        expected_owner="physician",
    ),
    # -------- Awaiting imaging: TTE for endocarditis ------------------------
    Template(
        name="ie_awaiting_tte",
        chief_complaint="Fever, IVDU, suspected endocarditis",
        note=(
            "HPI: 39yo male with history of IV drug use presents with fevers x 1 week.\n"
            "Exam: febrile, new systolic murmur at LSB. Track marks both arms.\n"
            "Labs: WBC 18, blood cultures growing gram-positive cocci in 3/3 bottles.\n"
            "Imaging: TTE ordered, scheduled for tomorrow. CXR clear.\n"
            "Assessment: suspected infective endocarditis.\n"
            "Plan: vancomycin + cefepime empiric. ID consult."
        ),
        icd10_hints=["I33.0"],
        truth_bottleneck="awaiting_imaging",
        expected_owner="physician",
    ),
    # -------- Dispo: dialysis chair, no outpatient slot ---------------------
    Template(
        name="dispo_dialysis_chair",
        chief_complaint="ESRD, dispo delayed by outpatient HD slot",
        note=(
            "HPI: 58yo male admitted for hyperkalemia, now corrected after dialysis. "
            "Medically ready for discharge.\n"
            "Exam: stable, no edema.\n"
            "Labs: K 4.2, Cr 6.8 (post-HD baseline).\n"
            "Assessment: ESRD, hyperkalemia resolved.\n"
            "Plan: medically optimized. Awaiting outpatient HD chair assignment — case "
            "management following, no slot available until next week. Insurance authorization in progress."
        ),
        icd10_hints=["N18.6", "Z99.2"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Dispo: TBI rehab placement ------------------------------------
    Template(
        name="dispo_rehab_tbi",
        chief_complaint="Post-TBI, awaiting rehab placement",
        note=(
            "HPI: 27yo male, status post MVC with traumatic brain injury 12 days ago. "
            "Cognitively improving. Medically stable.\n"
            "Exam: oriented x2, walks with assist, follows commands.\n"
            "Assessment: TBI, neurocognitive deficits, requires inpatient rehab.\n"
            "Plan: SNF placement requested 5 days ago. 3 SNFs declined due to insurance authorization. "
            "Case management following daily."
        ),
        icd10_hints=["S06.9X9A"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Readmit risk: COPD with no inhaler at home --------------------
    Template(
        name="copd_readmit_no_inhaler",
        chief_complaint="COPD readmit, lost inhaler",
        note=(
            "HPI: 67yo female with COPD, fourth admission this year for exacerbation. "
            "Reports running out of inhalers, no PCP follow-up in 6 months. Smoking 1ppd. "
            "Lives alone. Limited mobility, unable to get to pharmacy.\n"
            "Exam: improved, mild expiratory wheeze.\n"
            "Assessment: COPD, severe. Recurrent admissions, social factors.\n"
            "Plan: optimize inhaler regimen. Discharge to home with brief rehab if approved."
        ),
        icd10_hints=["J44.1"],
        truth_bottleneck="readmit_risk",
        expected_owner="case_manager",
    ),
    # -------- Clear: cellulitis ready for discharge -------------------------
    Template(
        name="clear_cellulitis",
        chief_complaint="Cellulitis, completed IV antibiotics",
        note=(
            "HPI: 52yo male, day 3 of cephalexin for lower extremity cellulitis. "
            "Erythema receding, no fever, tolerating PO.\n"
            "Exam: improving erythema, no streaking, no fluctuance.\n"
            "Assessment: cellulitis, resolving.\n"
            "Plan: transition to PO antibiotics. Discharge home with follow-up in 1 week."
        ),
        icd10_hints=["L03.115"],
        truth_bottleneck="clear",
        expected_owner="",
    ),
    # -------- Clear: chest pain ruled out -----------------------------------
    Template(
        name="clear_chest_pain_rule_out",
        chief_complaint="Chest pain, ruled out for ACS",
        note=(
            "HPI: 49yo male with atypical chest pain, fully ruled out with two negative troponins and "
            "normal stress test.\n"
            "Exam: nonfocal, comfortable.\n"
            "Labs: troponin x 2 negative.\n"
            "Imaging: stress echo no inducible ischemia.\n"
            "Assessment: non-cardiac chest pain, likely musculoskeletal.\n"
            "Plan: discharge home with PCP follow-up. NSAIDs as needed."
        ),
        icd10_hints=["R07.9"],
        truth_bottleneck="clear",
        expected_owner="",
    ),
    # -------- Sepsis already resolved (negative case, edge) -----------------
    Template(
        name="sepsis_resolved_negative",
        chief_complaint="Resolved sepsis from prior admission",
        note=(
            "HPI: 68yo female, hospital day 6, admitted for sepsis from UTI on day 1. "
            "Sepsis resolved with antibiotics. Afebrile for 72 hours. "
            "Hemodynamics back to baseline. Now medically ready.\n"
            "Exam: comfortable, vitals stable.\n"
            "Labs: WBC normalized at 7.4, lactate 1.2.\n"
            "Assessment: sepsis resolved. Awaiting SNF placement.\n"
            "Plan: SNF placement requested 2 days ago. Case management pursuing."
        ),
        icd10_hints=["A41.9", "N39.0"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Stroke window expired, no longer fires (negative) -------------
    Template(
        name="stroke_window_expired",
        chief_complaint="Old stroke, residual deficits, dispo",
        note=(
            "HPI: 73yo male, stroke 5 days ago. Deficits improving but residual. "
            "Medically ready.\n"
            "Exam: residual right-sided weakness 4/5, otherwise nonfocal.\n"
            "Assessment: ischemic stroke, residual deficits. Stroke window expired.\n"
            "Plan: PT/OT recommend acute rehab. Awaiting bed at rehab facility. "
            "Case management following."
        ),
        icd10_hints=["I69.351"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Multi-protocol case: sepsis + AKI -----------------------------
    Template(
        name="sepsis_aki_combo",
        chief_complaint="Septic shock with AKI",
        note=(
            "HPI: 64yo male with diabetes, presenting with septic shock from urinary source. "
            "Cr rising from 1.1 to 2.6 over 24h. Home meds include lisinopril, ibuprofen, "
            "and metformin.\n"
            "Exam: ill-appearing, BP 84/52 on 0.05 norepinephrine. HR 124.\n"
            "Labs: WBC 22, lactate 4.8, Cr 2.6, K 5.4. Blood cultures sent.\n"
            "Assessment: septic shock with AKI. Multifactorial.\n"
            "Plan: IV fluids 30 mL/kg given. Vancomycin and zosyn started. ICU admission."
        ),
        icd10_hints=["A41.9", "N17.9", "R65.21"],
        truth_bottleneck="missing_soc",
        truth_protocol="sepsis",
        expected_owner="physician",
        prior_notes=[
            PriorNote(
                hours_ago=12,
                note_text=(
                    "HPI: 64yo diabetic, fever and dysuria. BP 102/64, HR 98.\n"
                    "Labs: WBC 15, lactate 2.4, Cr 1.1, K 4.6.\n"
                    "Assessment: urinary sepsis, hemodynamically stable.\n"
                    "Plan: cultures sent, fluids, monitor."
                ),
            ),
        ],
    ),
    # -------- Awaiting consult: surgery, perforated viscus ------------------
    Template(
        name="perf_awaiting_surgery",
        chief_complaint="Free air on CT, surgery not yet seen",
        note=(
            "HPI: 58yo male presenting with sudden severe abdominal pain, peritoneal signs on exam.\n"
            "Exam: rigid abdomen, rebound tenderness, BP 102/68.\n"
            "Labs: WBC 16.4, lactate 2.8.\n"
            "Imaging: CT abdomen shows free air, concern for perforated viscus.\n"
            "Assessment: perforated viscus.\n"
            "Plan: NPO, IVF, broad-spectrum antibiotics. Surgical consult placed 90 min ago, "
            "awaiting callback. NG tube placed."
        ),
        icd10_hints=["K65.9"],
        truth_bottleneck="awaiting_consult",
        expected_owner="physician",
    ),
    # -------- Med risk: insulin without glucose monitoring ------------------
    Template(
        name="insulin_no_glucose_monitor",
        chief_complaint="Diabetic admission, hypoglycemia event",
        note=(
            "HPI: 76yo female with type 2 DM admitted for foot infection. NPO for procedure. "
            "Continued home insulin regimen including lantus 30u and aspart sliding scale.\n"
            "Exam: episode of hypoglycemia overnight, glucose 42, treated with D50.\n"
            "Labs: glucose 42 (overnight), now 156. A1c 9.8.\n"
            "Assessment: hypoglycemia related to insulin without adequate glucose monitoring.\n"
            "Plan: continue insulin, recheck POC glucose Q4."
        ),
        icd10_hints=["E11.9", "E16.2"],
        truth_bottleneck="med_risk",
        expected_owner="pharmacist",
    ),
    # -------- Dispo: language barrier, no interpreter -----------------------
    Template(
        name="dispo_language_barrier",
        chief_complaint="Discharge teaching delayed, no interpreter",
        note=(
            "HPI: 62yo female with new-onset CHF, medically optimized. Mandarin-speaking only. "
            "Family unable to be present for teaching today.\n"
            "Exam: stable, no edema.\n"
            "Assessment: HFpEF, ready for discharge.\n"
            "Plan: discharge teaching pending Mandarin interpreter availability. "
            "Family training not yet completed. Case management following."
        ),
        icd10_hints=["I50.32"],
        truth_bottleneck="dispo_delay",
        expected_owner="case_manager",
    ),
    # -------- Multi-bottleneck: med-risk and dispo, take med-risk first -----
    Template(
        name="med_risk_dispo_combo",
        chief_complaint="Discharge delayed by warfarin issue",
        note=(
            "HPI: 80yo female admitted for AFib, started on warfarin. INR today is 4.6 after "
            "starting bactrim 3 days ago. SNF placement also requested but pending.\n"
            "Exam: stable, no bleeding.\n"
            "Labs: INR 4.6 (target 2-3), hgb 11.0.\n"
            "Assessment: supratherapeutic INR from drug interaction.\n"
            "Plan: hold warfarin, stop bactrim. Recheck INR tomorrow. "
            "SNF placement also pending insurance authorization."
        ),
        icd10_hints=["I48.91", "D68.32"],
        truth_bottleneck="med_risk",
        expected_owner="pharmacist",
    ),
    # -------- Awaiting consult: vascular surgery, ischemic limb -------------
    Template(
        name="limb_ischemia_awaiting_vasc",
        chief_complaint="Acute limb ischemia",
        note=(
            "HPI: 70yo male with AFib, off anticoagulation, presents with cold pale right leg "
            "x 4 hours.\n"
            "Exam: right foot mottled, no pedal pulses bilaterally. Sensation decreased.\n"
            "Labs: lactate 2.2.\n"
            "Imaging: CTA shows right popliteal occlusion.\n"
            "Assessment: acute limb ischemia.\n"
            "Plan: heparin drip initiated. Vascular surgery consult placed 2h ago, awaiting callback. "
            "Patient NPO for OR."
        ),
        icd10_hints=["I74.3"],
        truth_bottleneck="awaiting_consult",
        expected_owner="physician",
    ),
]


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

@dataclass
class PatientNote:
    patient_id: str
    arrival_time: str
    age: int
    sex: str
    chief_complaint: str
    note_text: str
    icd10_hints: List[str]
    truth_bottleneck: str
    truth_protocol: str
    expected_owner: str
    template_name: str
    prior_notes: List[dict] = field(default_factory=list)  # [{hours_ago, note_text}]


def _alphabet_id(i: int) -> str:
    """Generate P-#### style synthetic IDs."""
    return f"P-{1000 + i:04d}"


def generate(n_per_template: int = 3) -> List[PatientNote]:
    """Materialize the dataset by lightly varying each template.

    Variations stay clinically plausible: age shifts, arrival times spread
    over the last 72h, occasional sex flip when not pathognomonic.

    Arrival times are anchored on the run time so the demo always shows
    fresh-looking arrivals (the analytics page bucketing depends on this).
    """
    notes: List[PatientNote] = []
    pid = 0
    base_time = datetime.utcnow()

    # Templates whose presentation depends on biological sex; don't flip.
    sex_locked = {"rlq_pain_awaiting_ct"}

    for tmpl in TEMPLATES:
        for _ in range(n_per_template):
            # Pull the seed age out of the note text (first occurrence "##yo")
            base_age = 50
            for tok in tmpl.note.split():
                if tok.endswith("yo") and tok[:-2].isdigit():
                    base_age = int(tok[:-2])
                    break

            age_jitter = random.randint(-4, 4)
            age = max(18, base_age + age_jitter)

            sex = "F" if "female" in tmpl.note.lower() else "M"
            if tmpl.name not in sex_locked and random.random() < 0.15:
                sex = "M" if sex == "F" else "F"

            # Spread arrivals across roughly the last 96 hours so the
            # arrival-age histogram has signal across all buckets.
            arrival = base_time - timedelta(
                hours=random.randint(1, 96),
                minutes=random.randint(0, 59),
            )

            notes.append(
                PatientNote(
                    patient_id=_alphabet_id(pid),
                    arrival_time=arrival.isoformat(timespec="minutes"),
                    age=age,
                    sex=sex,
                    chief_complaint=tmpl.chief_complaint,
                    note_text=tmpl.note,
                    icd10_hints=list(tmpl.icd10_hints),
                    truth_bottleneck=tmpl.truth_bottleneck,
                    truth_protocol=tmpl.truth_protocol,
                    expected_owner=tmpl.expected_owner,
                    template_name=tmpl.name,
                    prior_notes=[asdict(pn) for pn in tmpl.prior_notes],
                )
            )
            pid += 1

    random.shuffle(notes)
    return notes


def main() -> None:
    notes = generate(n_per_template=4)
    OUT_PATH.write_text(json.dumps([asdict(n) for n in notes], indent=2))
    print(f"Wrote {len(notes)} notional patient notes -> {OUT_PATH}")


if __name__ == "__main__":
    main()
