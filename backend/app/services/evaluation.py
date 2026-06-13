"""Classifier evaluation harness.

Scores the persisted triage results against the held-out truth labels that
ship with the corpus (Patient.truth_bottleneck, never exposed in the UI).
Reports accuracy, per-category precision/recall/F1, a sparse confusion
matrix, and owner-routing accuracy.

This keeps the product honest: the rules are deterministic and explainable,
so when they're wrong we can name the exact patients and templates they miss
(/eval/misses). Pure-python math — no sklearn dependency for the metrics.

Operational coordination tooling, NOT a clinical decision aid.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.orm import Patient, Triage
from app.services.bottleneck import BOTTLENECK_LABELS


NOTES_PATH = Path(__file__).parent.parent / "data" / "patient_notes.json"

# Canonical category -> owner routing (matches the README table). Used as a
# fallback for patients that are not present in the shipped corpus (e.g.
# test-seeded rows); corpus rows carry an explicit expected_owner field.
CANONICAL_OWNER: Dict[str, str] = {
    "missing_soc": "physician",
    "med_risk": "pharmacist",
    "awaiting_consult": "physician",
    "awaiting_imaging": "nurse",
    "readmit_risk": "case_manager",
    "dispo_delay": "case_manager",
    "clear": "",
}

_expected_owner_cache: Optional[Dict[str, str]] = None


def _expected_owner_map() -> Dict[str, str]:
    """Lazy-load {patient_id: expected_owner} from the corpus file."""
    global _expected_owner_cache
    if _expected_owner_cache is None:
        rows = json.loads(NOTES_PATH.read_text())
        _expected_owner_cache = {
            r["patient_id"]: r["expected_owner"]
            for r in rows
            if "expected_owner" in r
        }
    return _expected_owner_cache


def _expected_owner(patient_id: str, truth_category: str) -> str:
    corpus = _expected_owner_map()
    if patient_id in corpus:
        return corpus[patient_id]
    return CANONICAL_OWNER.get(truth_category, "")


def _f1(precision: float, recall: float) -> float:
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def evaluate_corpus(db: Session) -> Dict:
    """Score Triage.primary_category against Patient.truth_bottleneck for
    every patient carrying a truth label. Returns plain-dict metrics."""
    pairs = (
        db.query(Patient, Triage)
        .join(Triage, Triage.patient_id == Patient.id)
        .filter(Patient.truth_bottleneck.isnot(None))
        .all()
    )

    n = len(pairs)
    truth_counts: Counter[str] = Counter()
    pred_counts: Counter[str] = Counter()
    correct_counts: Counter[str] = Counter()
    confusion: Counter = Counter()
    owner_correct = 0

    for patient, triage in pairs:
        truth = patient.truth_bottleneck
        pred = triage.primary_category
        truth_counts[truth] += 1
        pred_counts[pred] += 1
        if truth == pred:
            correct_counts[truth] += 1
        confusion[(truth, pred)] += 1
        if triage.primary_owner == _expected_owner(patient.id, truth):
            owner_correct += 1

    accuracy = (sum(correct_counts.values()) / n) if n else 0.0

    # Canonical category order, then any stragglers (defensive).
    ordered = [c for c in BOTTLENECK_LABELS if c in truth_counts or c in pred_counts]
    ordered += sorted((set(truth_counts) | set(pred_counts)) - set(ordered))

    per_category: List[Dict] = []
    for cat in ordered:
        support = truth_counts[cat]
        precision = correct_counts[cat] / pred_counts[cat] if pred_counts[cat] else 0.0
        recall = correct_counts[cat] / support if support else 0.0
        per_category.append(
            {
                "category": cat,
                "precision": round(precision, 4),
                "recall": round(recall, 4),
                "f1": round(_f1(precision, recall), 4),
                "support": support,
            }
        )

    confusion_cells = [
        {"truth": truth, "predicted": pred, "count": count}
        for (truth, pred), count in sorted(confusion.items())
        if count
    ]

    return {
        "n": n,
        "accuracy": round(accuracy, 4),
        "per_category": per_category,
        "confusion": confusion_cells,
        "owner_routing": {
            "n": n,
            "accuracy": round(owner_correct / n, 4) if n else 0.0,
        },
    }


def misclassified(db: Session) -> List[Dict]:
    """Every disagreement between the engine and the held-out labels, by name.

    Two kinds of miss are reported, each tagged with ``miss_type``:

    - ``"category"`` — predicted bottleneck category != truth_bottleneck.
    - ``"owner"`` — predicted category is correct but the routed owner != the
      expected owner. On the shipped corpus these are exactly the 16
      awaiting_imaging rows (the corpus labels them physician; the engine
      routes imaging expediting to the floor nurse). We surface them here
      rather than relabel the data — honesty over a vanity 100%.

    Debugging honesty: every rule-edit regression shows up here by name.
    """
    pairs = (
        db.query(Patient, Triage)
        .join(Triage, Triage.patient_id == Patient.id)
        .filter(Patient.truth_bottleneck.isnot(None))
        .all()
    )
    out: List[Dict] = []
    for patient, triage in pairs:
        truth = patient.truth_bottleneck
        if triage.primary_category != truth:
            out.append(
                {
                    "patient_id": patient.id,
                    "miss_type": "category",
                    "truth": truth,
                    "predicted": triage.primary_category,
                    "urgency": triage.primary_urgency,
                    "template_name": patient.template_name,
                }
            )
            continue
        # Category is right — check owner routing.
        expected_owner = _expected_owner(patient.id, truth)
        if triage.primary_owner != expected_owner:
            out.append(
                {
                    "patient_id": patient.id,
                    "miss_type": "owner",
                    "truth": expected_owner,
                    "predicted": triage.primary_owner,
                    "urgency": triage.primary_urgency,
                    "template_name": patient.template_name,
                }
            )
    out.sort(key=lambda m: (m["miss_type"], m["patient_id"]))
    return out
