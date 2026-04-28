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


def _alphabet_id(i: int) -> str:
    """Generate P-#### style synthetic IDs."""
    return f"P-{1000 + i:04d}"


def generate(n_per_template: int = 3) -> List[PatientNote]:
    """Materialize the dataset by lightly varying each template.

    Variations stay clinically plausible: age shifts, arrival times spread
    over the last 36h, occasional sex flip when not pathognomonic.
    """
    notes: List[PatientNote] = []
    pid = 0
    base_time = datetime(2026, 4, 27, 7, 0)

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

            arrival = base_time - timedelta(
                hours=random.randint(1, 36),
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
                )
            )
            pid += 1

    random.shuffle(notes)
    return notes


def main() -> None:
    notes = generate(n_per_template=3)
    OUT_PATH.write_text(json.dumps([asdict(n) for n in notes], indent=2))
    print(f"Wrote {len(notes)} notional patient notes -> {OUT_PATH}")


if __name__ == "__main__":
    main()
