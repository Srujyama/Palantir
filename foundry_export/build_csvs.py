"""
Generate Pipeline Builder-ready CSVs from the local backend data.

Outputs five CSVs in this folder:

  patients.csv          one row per patient — demographics, arrival, chief complaint
  notes.csv             one row per note — patient_id + raw note_text
  protocols.csv         one row per (protocol, expected_action) pair
  icd10_reference.csv   the 39-code reference set
  eval_labels.csv       held-out ground truth per patient — kept OUT of
                        patients.csv so the Workshop Patient object never
                        carries labels; wire this only to the eval harness.

Run:  python build_csvs.py
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" / "app"
OUT = Path(__file__).resolve().parent

# ---------- patients + notes ----------
notes = json.loads((BACKEND / "data" / "patient_notes.json").read_text())

with (OUT / "patients.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["patient_id", "arrival_time", "age", "sex", "chief_complaint"])
    for n in notes:
        w.writerow([
            n["patient_id"],
            n["arrival_time"],
            n["age"],
            n["sex"],
            n["chief_complaint"],
        ])

with (OUT / "notes.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["patient_id", "note_text"])
    for n in notes:
        w.writerow([n["patient_id"], n["note_text"]])

# ---------- eval labels (ground truth — separate from the Patient object) ----------
with (OUT / "eval_labels.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "patient_id", "truth_bottleneck", "truth_protocol", "expected_owner",
        "icd10_hints",
    ])
    for n in notes:
        w.writerow([
            n["patient_id"],
            n.get("truth_bottleneck", ""),
            n.get("truth_protocol", ""),
            n.get("expected_owner", ""),
            "|".join(n.get("icd10_hints", [])),
        ])

# ---------- protocols ----------
# Re-import protocol library from backend
import sys
sys.path.insert(0, str(ROOT / "backend"))
from app.protocols.library import PROTOCOLS  # type: ignore

with (OUT / "protocols.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow([
        "protocol_key", "protocol_name", "time_window_hours", "owner",
        "urgency_if_incomplete", "citation",
        "trigger_patterns",
        "action_key", "action_label", "action_documented_patterns", "action_severity",
    ])
    for p in PROTOCOLS:
        triggers = "|".join(p.triggers)
        for a in p.expected_actions:
            w.writerow([
                p.key, p.name, p.time_window_hours, p.owner,
                p.urgency_if_incomplete, p.citation,
                triggers,
                a.key, a.label, "|".join(a.documented_patterns), a.severity,
            ])

# ---------- icd10 reference ----------
icd = json.loads((BACKEND / "data" / "icd10_reference.json").read_text())
with (OUT / "icd10_reference.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["code", "description", "category"])
    for row in icd:
        w.writerow([row["code"], row["description"], row.get("category", "")])

print(f"Wrote {len(notes)} patients, {len(notes)} notes, "
      f"{len(notes)} eval labels, "
      f"{sum(len(p.expected_actions) for p in PROTOCOLS)} protocol-action rows "
      f"({len(PROTOCOLS)} protocols), "
      f"{len(icd)} ICD-10 codes to {OUT}")
