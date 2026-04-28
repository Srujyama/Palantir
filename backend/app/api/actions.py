"""Action workflow endpoints: create, update, list."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, Patient
from app.models.schemas import ActionCreate, ActionResponse, ActionUpdate


router = APIRouter(prefix="/actions", tags=["actions"])


VALID_STATUSES = {"open", "in_progress", "resolved", "escalated"}


def _to_response(a: Action) -> ActionResponse:
    return ActionResponse(
        id=a.id, patient_id=a.patient_id, title=a.title, description=a.description,
        owner=a.owner, urgency=a.urgency, status=a.status,
        source_category=a.source_category,
        created_at=a.created_at, updated_at=a.updated_at,
    )


@router.get("", response_model=List[ActionResponse])
def list_actions(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
):
    q = db.query(Action)
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(400, f"invalid status: {status}")
        q = q.filter(Action.status == status)
    if owner:
        q = q.filter(Action.owner == owner)
    rows = q.order_by(Action.created_at.desc()).all()
    return [_to_response(r) for r in rows]


@router.post("/{patient_id}", response_model=ActionResponse, status_code=201)
def create_action(patient_id: str, body: ActionCreate, db: Session = Depends(get_db)):
    if not db.query(Patient).filter(Patient.id == patient_id).first():
        raise HTTPException(404, f"patient {patient_id} not found")
    a = Action(
        patient_id=patient_id,
        title=body.title,
        description=body.description,
        owner=body.owner,
        urgency=body.urgency,
        status="open",
        source_category=body.source_category,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return _to_response(a)


@router.patch("/{action_id}", response_model=ActionResponse)
def update_action(action_id: int, body: ActionUpdate, db: Session = Depends(get_db)):
    a = db.query(Action).filter(Action.id == action_id).one_or_none()
    if not a:
        raise HTTPException(404, f"action {action_id} not found")
    if body.status:
        if body.status not in VALID_STATUSES:
            raise HTTPException(400, f"invalid status: {body.status}")
        a.status = body.status
    if body.owner is not None:
        a.owner = body.owner
    a.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(a)
    return _to_response(a)
