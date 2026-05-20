"""Action workflow endpoints: create, update, list, bulk, audit log."""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, ActionEvent, Patient
from app.models.schemas import (
    ActionCreate,
    ActionEventResponse,
    ActionResponse,
    ActionUpdate,
)


router = APIRouter(prefix="/actions", tags=["actions"])


VALID_STATUSES = {"open", "in_progress", "resolved", "escalated"}


def _to_response(a: Action) -> ActionResponse:
    return ActionResponse(
        id=a.id, patient_id=a.patient_id, title=a.title, description=a.description,
        owner=a.owner, urgency=a.urgency, status=a.status,
        source_category=a.source_category,
        created_at=a.created_at, updated_at=a.updated_at,
    )


def _log_event(
    db: Session,
    action: Action,
    event_type: str,
    from_value: Optional[str] = None,
    to_value: Optional[str] = None,
    actor: str = "charge-rn",
    note: Optional[str] = None,
) -> ActionEvent:
    ev = ActionEvent(
        action_id=action.id,
        event_type=event_type,
        from_value=from_value,
        to_value=to_value,
        actor=actor,
        note=note,
    )
    db.add(ev)
    return ev


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


class BulkCreateBody(BaseModel):
    patient_ids: List[str]
    title: str
    description: str
    owner: str
    urgency: str
    source_category: str


class BulkUpdateBody(BaseModel):
    action_ids: List[int]
    status: Optional[str] = None
    owner: Optional[str] = None


# Bulk routes must come *before* path-parameter routes so they match first.

@router.post("/bulk", response_model=List[ActionResponse], status_code=201)
def bulk_create(body: BulkCreateBody, db: Session = Depends(get_db)):
    """Create the same action against multiple patients in one transaction.

    Real workflow: charge nurse selects a row range from the queue and
    routes all of them to one owner (e.g. case manager for all dispo holds).
    """
    if not body.patient_ids:
        raise HTTPException(400, "patient_ids required")
    existing = {p.id for p in db.query(Patient).filter(Patient.id.in_(body.patient_ids)).all()}
    missing = sorted(set(body.patient_ids) - existing)
    if missing:
        raise HTTPException(404, f"patients not found: {missing}")
    created: List[Action] = []
    for pid in body.patient_ids:
        a = Action(
            patient_id=pid,
            title=body.title,
            description=body.description,
            owner=body.owner,
            urgency=body.urgency,
            status="open",
            source_category=body.source_category,
        )
        db.add(a)
        db.flush()
        _log_event(db, a, event_type="created", to_value="open", note="bulk-created")
        created.append(a)
    db.commit()
    return [_to_response(a) for a in created]


@router.patch("/bulk", response_model=List[ActionResponse])
def bulk_update(body: BulkUpdateBody, db: Session = Depends(get_db)):
    if not body.action_ids:
        raise HTTPException(400, "action_ids required")
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(400, f"invalid status: {body.status}")
    rows = db.query(Action).filter(Action.id.in_(body.action_ids)).all()
    out: List[Action] = []
    for a in rows:
        if body.status and body.status != a.status:
            _log_event(
                db, a, event_type="status_change",
                from_value=a.status, to_value=body.status, note="bulk-update",
            )
            a.status = body.status
        if body.owner and body.owner != a.owner:
            _log_event(
                db, a, event_type="reassigned",
                from_value=a.owner, to_value=body.owner, note="bulk-update",
            )
            a.owner = body.owner
        a.updated_at = datetime.utcnow()
        out.append(a)
    db.commit()
    return [_to_response(a) for a in out]


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
    db.flush()
    _log_event(db, a, event_type="created", to_value="open")
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
        if body.status != a.status:
            _log_event(
                db, a, event_type="status_change",
                from_value=a.status, to_value=body.status,
            )
            a.status = body.status
    if body.owner is not None and body.owner != a.owner:
        _log_event(
            db, a, event_type="reassigned",
            from_value=a.owner, to_value=body.owner,
        )
        a.owner = body.owner
    a.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(a)
    return _to_response(a)


@router.get("/{action_id}/events", response_model=List[ActionEventResponse])
def action_events(action_id: int, db: Session = Depends(get_db)):
    a = db.query(Action).filter(Action.id == action_id).one_or_none()
    if not a:
        raise HTTPException(404, f"action {action_id} not found")
    rows = (
        db.query(ActionEvent)
        .filter(ActionEvent.action_id == action_id)
        .order_by(ActionEvent.created_at.asc())
        .all()
    )
    return [
        ActionEventResponse(
            id=ev.id, action_id=ev.action_id, event_type=ev.event_type,
            from_value=ev.from_value, to_value=ev.to_value,
            actor=ev.actor, note=ev.note, created_at=ev.created_at,
        )
        for ev in rows
    ]


