"""
Curated ICD-10 reference set for the Bottleneck Radar.

This is a focused subset (not the full ~70k CMS list) chosen to cover the
conditions appearing in the notional patient notes plus common admissions
diagnoses. Each entry includes a short clinical description used both for
display and as the corpus for TF-IDF retrieval over note text.

Source: descriptions adapted from public CMS ICD-10-CM tabular list.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, TypedDict

OUT_PATH = Path(__file__).parent / "icd10_reference.json"


class ICD10Entry(TypedDict):
    code: str
    description: str
    category: str


CODES: List[ICD10Entry] = [
    # Sepsis / infection
    {"code": "A41.9", "description": "Sepsis, unspecified organism", "category": "infection"},
    {"code": "R65.20", "description": "Severe sepsis without septic shock", "category": "infection"},
    {"code": "R65.21", "description": "Severe sepsis with septic shock", "category": "infection"},
    {"code": "N39.0", "description": "Urinary tract infection, site not specified", "category": "infection"},
    {"code": "N30.00", "description": "Acute cystitis without hematuria", "category": "infection"},
    {"code": "J18.9", "description": "Pneumonia, unspecified organism", "category": "infection"},
    {"code": "J15.9", "description": "Unspecified bacterial pneumonia", "category": "infection"},

    # Cardiac
    {"code": "I21.4", "description": "Non-ST elevation (NSTEMI) myocardial infarction", "category": "cardiac"},
    {"code": "I21.3", "description": "ST elevation myocardial infarction (STEMI), unspecified site", "category": "cardiac"},
    {"code": "I20.0", "description": "Unstable angina", "category": "cardiac"},
    {"code": "I50.32", "description": "Chronic diastolic (congestive) heart failure", "category": "cardiac"},
    {"code": "I50.22", "description": "Chronic systolic (congestive) heart failure", "category": "cardiac"},
    {"code": "I48.91", "description": "Unspecified atrial fibrillation", "category": "cardiac"},
    {"code": "I49.8", "description": "Other specified cardiac arrhythmias", "category": "cardiac"},

    # Stroke / neuro
    {"code": "I63.9", "description": "Cerebral infarction, unspecified", "category": "neuro"},
    {"code": "G81.91", "description": "Hemiplegia, unspecified affecting right dominant side", "category": "neuro"},
    {"code": "R56.9", "description": "Unspecified convulsions", "category": "neuro"},
    {"code": "G40.909", "description": "Epilepsy, unspecified, not intractable, without status epilepticus", "category": "neuro"},
    {"code": "G43.909", "description": "Migraine, unspecified, not intractable, without status migrainosus", "category": "neuro"},
    {"code": "R45.851", "description": "Suicidal ideations", "category": "psych"},

    # Renal
    {"code": "N17.9", "description": "Acute kidney failure, unspecified", "category": "renal"},
    {"code": "N18.6", "description": "End stage renal disease", "category": "renal"},

    # Endocrine
    {"code": "E10.10", "description": "Type 1 diabetes mellitus with ketoacidosis without coma", "category": "endocrine"},
    {"code": "E11.9", "description": "Type 2 diabetes mellitus without complications", "category": "endocrine"},
    {"code": "E11.65", "description": "Type 2 diabetes mellitus with hyperglycemia", "category": "endocrine"},

    # Respiratory
    {"code": "J44.1", "description": "Chronic obstructive pulmonary disease with (acute) exacerbation", "category": "respiratory"},
    {"code": "J45.901", "description": "Unspecified asthma with (acute) exacerbation", "category": "respiratory"},
    {"code": "Z99.81", "description": "Dependence on supplemental oxygen", "category": "respiratory"},

    # GI / surgical
    {"code": "K35.80", "description": "Unspecified acute appendicitis", "category": "surgical"},
    {"code": "K92.2", "description": "Gastrointestinal hemorrhage, unspecified", "category": "gi"},
    {"code": "R10.31", "description": "Right lower quadrant pain", "category": "symptom"},

    # Trauma / ortho
    {"code": "S72.141A", "description": "Displaced intertrochanteric fracture of left femur, initial", "category": "trauma"},
    {"code": "Z47.1", "description": "Aftercare following joint replacement surgery", "category": "post_op"},

    # Adverse effects / poisoning
    {"code": "T36.91XA", "description": "Adverse effect of unspecified systemic antibiotic, initial", "category": "adverse_effect"},
    {"code": "T39.395A", "description": "Adverse effect of other propionic acid derivatives, initial", "category": "adverse_effect"},
    {"code": "T50.905A", "description": "Adverse effect of unspecified drugs, medicaments and biological substances, initial", "category": "adverse_effect"},
    {"code": "D62", "description": "Acute posthemorrhagic anemia", "category": "hematology"},

    # Social / dispo
    {"code": "Z74.09", "description": "Other reduced mobility", "category": "social"},
    {"code": "Z91.120", "description": "Patient's intentional underdosing of medication regimen due to financial hardship", "category": "social"},
]


def write() -> None:
    OUT_PATH.write_text(json.dumps(CODES, indent=2))
    print(f"Wrote {len(CODES)} ICD-10 reference codes -> {OUT_PATH}")


if __name__ == "__main__":
    write()
