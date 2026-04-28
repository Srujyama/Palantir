"""End-to-end pipeline that takes a Patient row, runs extraction +
classification + ICD matching, and persists the Triage row.

Kept in one place so both the ingest script and the /reprocess endpoint hit
the same code path.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.orm import Patient, Triage
from app.nlp.extractor import extract
from app.nlp.icd_matcher import matcher
from app.services.bottleneck import classify


def run(db: Session, patient: Patient) -> Triage:
    extraction = extract(patient.note_text)
    triage = classify(patient.note_text, extraction)
    icd_matches = matcher().match(patient.note_text, k=5)

    payload = triage.to_dict()
    extraction_payload = extraction.to_dict()
    icd_payload = [
        {
            "code": m.code,
            "description": m.description,
            "score": m.score,
            "category": m.category,
        }
        for m in icd_matches
    ]

    existing = db.query(Triage).filter(Triage.patient_id == patient.id).one_or_none()
    if existing:
        existing.primary_category = triage.primary.category
        existing.primary_label = triage.primary.label
        existing.primary_urgency = triage.primary.urgency
        existing.primary_owner = triage.primary.owner
        existing.primary_action = triage.primary.recommended_action
        existing.primary_rationale = triage.primary.rationale
        existing.payload = payload
        existing.extraction = extraction_payload
        existing.icd_candidates = icd_payload
        return existing

    row = Triage(
        patient_id=patient.id,
        primary_category=triage.primary.category,
        primary_label=triage.primary.label,
        primary_urgency=triage.primary.urgency,
        primary_owner=triage.primary.owner,
        primary_action=triage.primary.recommended_action,
        primary_rationale=triage.primary.rationale,
        payload=payload,
        extraction=extraction_payload,
        icd_candidates=icd_payload,
    )
    db.add(row)
    return row
