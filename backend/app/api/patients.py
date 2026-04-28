"""Patient queue + detail endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, Patient, Triage
from app.models.schemas import (
    ActionResponse,
    BottleneckPayload,
    ICDCandidate,
    PatientDetail,
    PatientSummary,
    ProtocolMatchPayload,
    SilentFailurePayload,
    Span,
    WhyStuckResponse,
)


router = APIRouter(prefix="/patients", tags=["patients"])


URGENCY_ORDER = {"red": 0, "amber": 1, "green": 2}


def _open_actions_count(db: Session, patient_id: str) -> int:
    return (
        db.query(func.count(Action.id))
        .filter(Action.patient_id == patient_id, Action.status.in_(["open", "in_progress"]))
        .scalar()
        or 0
    )


def _silent_failure_count(triage: Triage) -> int:
    return len(triage.payload.get("silent_failures", []))


@router.get("", response_model=List[PatientSummary])
def list_patients(
    db: Session = Depends(get_db),
    urgency: Optional[str] = Query(None, regex="^(red|amber|green)$"),
    owner: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None, min_length=1, max_length=80),
):
    q = db.query(Patient).join(Triage)
    if urgency:
        q = q.filter(Triage.primary_urgency == urgency)
    if owner:
        q = q.filter(Triage.primary_owner == owner)
    if category:
        q = q.filter(Triage.primary_category == category)
    if search:
        like = f"%{search.lower()}%"
        q = q.filter(
            (func.lower(Patient.id).like(like))
            | (func.lower(Patient.chief_complaint).like(like))
        )

    patients = q.all()
    summaries: List[PatientSummary] = []
    for p in patients:
        t = p.triage
        summaries.append(
            PatientSummary(
                id=p.id,
                age=p.age,
                sex=p.sex,
                chief_complaint=p.chief_complaint,
                arrival_time=p.arrival_time,
                primary_category=t.primary_category,
                primary_label=t.primary_label,
                primary_urgency=t.primary_urgency,
                primary_owner=t.primary_owner,
                primary_action=t.primary_action,
                open_actions=_open_actions_count(db, p.id),
                silent_failure_count=_silent_failure_count(t),
            )
        )

    summaries.sort(key=lambda s: (URGENCY_ORDER[s.primary_urgency], s.arrival_time))
    return summaries


@router.get("/{patient_id}", response_model=PatientDetail)
def patient_detail(patient_id: str, db: Session = Depends(get_db)):
    p = db.query(Patient).filter(Patient.id == patient_id).one_or_none()
    if not p:
        raise HTTPException(404, f"Patient {patient_id} not found")
    t = p.triage
    payload = t.payload
    return PatientDetail(
        id=p.id,
        age=p.age,
        sex=p.sex,
        chief_complaint=p.chief_complaint,
        arrival_time=p.arrival_time,
        note_text=p.note_text,
        primary=BottleneckPayload(**payload["primary"]),
        secondary=[BottleneckPayload(**b) for b in payload["secondary"]],
        silent_failures=[SilentFailurePayload(**sf) for sf in payload["silent_failures"]],
        protocol_matches=[ProtocolMatchPayload(**pm) for pm in payload["protocol_matches"]],
        icd_candidates=[ICDCandidate(**c) for c in t.icd_candidates],
        extraction=t.extraction,
        actions=[
            ActionResponse(
                id=a.id, patient_id=a.patient_id, title=a.title, description=a.description,
                owner=a.owner, urgency=a.urgency, status=a.status,
                source_category=a.source_category,
                created_at=a.created_at, updated_at=a.updated_at,
            )
            for a in sorted(p.actions, key=lambda a: a.created_at, reverse=True)
        ],
    )


@router.get("/{patient_id}/why", response_model=WhyStuckResponse)
def why_stuck(patient_id: str, db: Session = Depends(get_db)):
    """Generates the 'Why is this patient stuck?' narrative.

    Deterministic — composed from the rationale strings of the primary and
    contributing bottlenecks, plus any silent failures. No LLM black box; the
    user can trace every sentence to a source signal.
    """
    p = db.query(Patient).filter(Patient.id == patient_id).one_or_none()
    if not p:
        raise HTTPException(404, f"Patient {patient_id} not found")
    payload = p.triage.payload
    primary = BottleneckPayload(**payload["primary"])
    secondary = [BottleneckPayload(**b) for b in payload["secondary"]]
    silent = [SilentFailurePayload(**sf) for sf in payload["silent_failures"]]

    bullets: List[str] = [primary.rationale]
    bullets.extend(b.rationale for b in secondary)
    if silent:
        for sf in silent:
            bullets.append(
                f"{sf.protocol_name}: required step “{sf.missing_action}” "
                f"is not documented (per {sf.citation})."
            )

    summary = (
        f"Patient {p.id} is held by {primary.label.lower()}: "
        f"{primary.recommended_action} "
        f"(owner: {primary.owner or 'unassigned'})."
    )

    return WhyStuckResponse(
        patient_id=p.id,
        summary=summary,
        bullet_points=bullets,
        primary=primary,
        contributing=secondary,
        silent_failures=silent,
    )
