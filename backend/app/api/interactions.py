"""Drug-interaction screening endpoint.

Re-runs the (fast, pure) extractor on the patient's note and screens it
against the citation-backed interaction rule table. Every flag carries the
medications involved with their evidence spans, the lab/symptom context
evidence, a mechanism, a pharmacist-voiced recommendation, and a citation.

Deterministic and explainable — an operational coordination signal for the
pharmacist queue, NOT a clinical decision aid.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Patient
from app.nlp.extractor import extract
from app.services.interactions import screen


router = APIRouter(prefix="/patients", tags=["interactions"])


class SpanModel(BaseModel):
    start: int
    end: int
    text: str


class MedInvolvedModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    drug_class: str = Field(alias="class")
    evidence: SpanModel


class InteractionFlagModel(BaseModel):
    rule_key: str
    name: str
    severity: str            # red | amber
    mechanism: str
    recommendation: str
    citation: str
    meds_involved: List[MedInvolvedModel]
    context_evidence: List[SpanModel] = Field(default_factory=list)


class InteractionScreenResponse(BaseModel):
    patient_id: str
    flags: List[InteractionFlagModel]


@router.get("/{patient_id}/interactions", response_model=InteractionScreenResponse)
def patient_interactions(patient_id: str, db: Session = Depends(get_db)):
    """Screen a patient's note for medication-interaction flags.

    Extraction is re-run live on the stored note (pure and fast) so the
    screen always reflects the current note text, not a stale payload.
    """
    p = db.query(Patient).filter(Patient.id == patient_id).one_or_none()
    if not p:
        raise HTTPException(404, f"Patient {patient_id} not found")
    ext = extract(p.note_text)
    flags = screen(ext, p.note_text)
    return InteractionScreenResponse(
        patient_id=p.id,
        flags=[InteractionFlagModel(**f.to_dict()) for f in flags],
    )
