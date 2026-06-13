"""Provenance / audit endpoints.

Exposes the auditability guarantee over HTTP, read-only:

  GET /audit/patient/{id}    full chain-of-custody for one patient — every
                             signal traced to a citation and verified
                             evidence span(s).
  GET /audit/corpus/summary  corpus-wide provenance health: pct_cited and
                             pct_verified, the numbers that back the
                             "verifiable, not a black box" thesis.

Both mirror app/api/patients.py: get_db dependency, 404 on missing patient,
no mutation. No classifier re-run, no LLM — just the materialized triage
payload re-checked against the immutable note.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.services import audit


router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/patient/{patient_id}")
def patient_audit(patient_id: str, db: Session = Depends(get_db)):
    """Provenance export for one patient.

    For the primary + secondary bottlenecks and every silent failure, returns
    the signal, category, urgency, owner, recommended_action, citation, and
    each evidence span with a `verified` boolean (note[start:end] == text).
    404 if the patient does not exist.
    """
    result = audit.build_patient_audit(db, patient_id)
    if result is None:
        raise HTTPException(404, f"Patient {patient_id} not found")
    return result.to_dict()


@router.get("/corpus/summary")
def corpus_summary(db: Session = Depends(get_db)):
    """Corpus-wide provenance health metrics.

    Returns n_patients, n_signals, n_with_citation, pct_cited,
    n_evidence_spans, n_verified_spans, pct_verified, plus any unverified
    spans (empty in a healthy corpus; each entry is a located, real defect).
    """
    return audit.build_corpus_summary(db)
