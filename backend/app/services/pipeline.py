"""End-to-end pipeline that takes a Patient row, runs extraction +
classification + ICD matching, and persists the Triage row.

Kept in one place so the ingest script, the live-tick simulator, and the
sandbox all share one code path.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.models.orm import NoteVersion, Patient, Triage
from app.nlp.extractor import extract
from app.nlp.icd_matcher import matcher
from app.services.bottleneck import classify
from app.services import trends as trends_service


def _compute_trends(db: Session, patient: Patient) -> dict:
    """Build the trajectory payload from prior notes + the current note.

    Prior notes are read here ONLY to narrate history; they never reach
    classify(). A patient with no priors yields a well-formed empty payload.
    """
    priors = (
        db.query(NoteVersion)
        .filter(NoteVersion.patient_id == patient.id)
        .order_by(NoteVersion.sequence)
        .all()
    )
    note_inputs = [
        trends_service.NoteInput(
            note_text=nv.note_text,
            hours_ago=nv.hours_ago,
            captured_at=nv.captured_at,
        )
        for nv in priors
    ]
    note_inputs.append(
        trends_service.NoteInput(
            note_text=patient.note_text,
            hours_ago=0,
            captured_at=patient.arrival_time,
        )
    )
    return trends_service.compute(note_inputs)


def run(db: Session, patient: Patient) -> Triage:
    extraction = extract(patient.note_text)
    triage = classify(patient.note_text, extraction)
    icd_matches = matcher().match(patient.note_text, k=5)
    trends_payload = _compute_trends(db, patient)

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
        existing.trends = trends_payload
        existing.computed_at = datetime.utcnow()
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
        trends=trends_payload,
    )
    db.add(row)
    return row
