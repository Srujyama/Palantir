"""Action workflow endpoints: create, update, list, bulk, notes, SLA sweep, audit log.

Actions carry an SLA deadline (policy table in app.services.sla) and move
through an explicit state machine. Every mutation writes an ActionEvent audit
row with the acting user, so the lifecycle is fully traceable. This is an
operational coordination surface, not a clinical decision aid.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, ActionEvent, Patient
from app.models.schemas import (
    VALID_OWNERS,
    VALID_URGENCIES,
    ActionCreate,
    ActionEventResponse,
    ActionNoteCreate,
    ActionResponse,
    ActionUpdate,
    BulkUpdateResponse,
    SweepResponse,
)
from app.services import sla


router = APIRouter(prefix="/actions", tags=["actions"])


VALID_STATUSES = {"open", "in_progress", "resolved", "escalated"}

# Explicit state machine. Keys are current status, values are the statuses a
# caller may move to. "resolved -> open" is the reopen path.
ALLOWED_TRANSITIONS: Dict[str, set] = {
    "open": {"in_progress", "resolved", "escalated"},
    "in_progress": {"open", "resolved", "escalated"},
    "escalated": {"in_progress", "resolved"},
    "resolved": {"open"},
}


def _to_response(a: Action, now: Optional[datetime] = None) -> ActionResponse:
    now = now or datetime.utcnow()
    return ActionResponse(
        id=a.id, patient_id=a.patient_id, title=a.title, description=a.description,
        owner=a.owner, urgency=a.urgency, status=a.status,
        source_category=a.source_category,
        sla_minutes=a.sla_minutes,
        due_at=a.due_at,
        escalation_level=a.escalation_level or 0,
        overdue=sla.is_overdue(a, now),
        minutes_remaining=sla.minutes_remaining(a, now),
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


def _check_transition(current: str, target: str) -> None:
    """Raise 422 unless `current -> target` is a legal state-machine move."""
    allowed = ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise HTTPException(
            422,
            f"invalid transition {current} -> {target}; "
            f"allowed from {current}: {sorted(allowed) or 'none'}",
        )


def _apply_status_change(
    db: Session, a: Action, target: str, actor: str, note: Optional[str] = None
) -> None:
    """Apply a validated status transition and write the audit row."""
    _log_event(
        db, a, event_type="status_change",
        from_value=a.status, to_value=target, actor=actor, note=note,
    )
    if target == "escalated":
        a.escalation_level = (a.escalation_level or 0) + 1
    a.status = target


def _new_action(patient_id: str, body_title: str, body_description: str,
                owner: str, urgency: str, source_category: str) -> Action:
    """Build an Action with its SLA window stamped from the policy table."""
    created_at = datetime.utcnow()
    minutes = sla.sla_minutes_for(source_category, urgency)
    return Action(
        patient_id=patient_id,
        title=body_title,
        description=body_description,
        owner=owner,
        urgency=urgency,
        status="open",
        source_category=source_category,
        sla_minutes=minutes,
        due_at=sla.compute_due_at(created_at, source_category, urgency),
        escalation_level=0,
        created_at=created_at,
        updated_at=created_at,
    )


@router.get("", response_model=List[ActionResponse])
def list_actions(
    db: Session = Depends(get_db),
    status: Optional[str] = Query(None),
    owner: Optional[str] = Query(None),
    overdue: Optional[bool] = Query(None),
):
    """List all actions with SLA state. Sorted breached-first, then by deadline."""
    q = db.query(Action)
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(400, f"invalid status: {status}")
        q = q.filter(Action.status == status)
    if owner:
        q = q.filter(Action.owner == owner)
    now = datetime.utcnow()
    responses = [_to_response(r, now) for r in q.all()]
    if overdue is not None:
        responses = [r for r in responses if r.overdue == overdue]
    # Overdue first, then due_at ascending with nulls last, then newest first.
    responses.sort(
        key=lambda r: (
            not r.overdue,
            r.due_at is None,
            r.due_at or datetime.max,
        )
    )
    return responses


class BulkCreateBody(BaseModel):
    patient_ids: List[str]
    title: str
    description: str
    owner: str
    urgency: str
    source_category: str
    actor: str = "charge-rn"

    @field_validator("owner")
    @classmethod
    def _owner_valid(cls, v: str) -> str:
        if v not in VALID_OWNERS:
            raise ValueError(f"owner must be one of {sorted(VALID_OWNERS)}")
        return v

    @field_validator("urgency")
    @classmethod
    def _urgency_valid(cls, v: str) -> str:
        if v not in VALID_URGENCIES:
            raise ValueError(f"urgency must be one of {sorted(VALID_URGENCIES)}")
        return v


class BulkUpdateBody(BaseModel):
    action_ids: List[int]
    status: Optional[str] = None
    owner: Optional[str] = None
    actor: str = "charge-rn"

    @field_validator("owner")
    @classmethod
    def _owner_valid(cls, v):
        if v is not None and v not in VALID_OWNERS:
            raise ValueError(f"owner must be one of {sorted(VALID_OWNERS)}")
        return v


# Static routes must come *before* path-parameter routes so they match first.

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
        a = _new_action(pid, body.title, body.description, body.owner,
                        body.urgency, body.source_category)
        db.add(a)
        db.flush()
        _log_event(db, a, event_type="created", to_value="open",
                   actor=body.actor, note="bulk-created")
        created.append(a)
    db.commit()
    return [_to_response(a) for a in created]


@router.patch("/bulk", response_model=BulkUpdateResponse)
def bulk_update(body: BulkUpdateBody, db: Session = Depends(get_db)):
    """Bulk status/owner change with a per-id report.

    Nothing is silently ignored. Each requested id resolves to exactly one of:
    - `updated` — a status and/or owner change was actually applied;
    - `missing` — the id does not exist;
    - `skipped` — no change took effect, with the reason. A row whose status
      transition is illegal is skipped as a whole; if the same request also
      asked for an owner reassignment, the reason says so explicitly (we do
      not half-apply). A row already in the requested state is skipped "no-op".
    Duplicate ids in the request are collapsed to one.
    """
    if not body.action_ids:
        raise HTTPException(400, "action_ids required")
    if body.status and body.status not in VALID_STATUSES:
        raise HTTPException(400, f"invalid status: {body.status}")
    unique_ids = list(dict.fromkeys(body.action_ids))  # de-dup, preserve order
    rows = db.query(Action).filter(Action.id.in_(unique_ids)).all()
    by_id = {a.id: a for a in rows}
    missing = sorted(set(unique_ids) - set(by_id))
    updated: List[Action] = []
    skipped: List[Dict[str, Any]] = []
    for aid in unique_ids:
        a = by_id.get(aid)
        if a is None:
            continue
        wants_status = bool(body.status) and body.status != a.status
        wants_owner = bool(body.owner) and body.owner != a.owner

        if wants_status:
            allowed = ALLOWED_TRANSITIONS.get(a.status, set())
            if body.status not in allowed:
                reason = (
                    f"invalid transition {a.status} -> {body.status}; "
                    f"allowed from {a.status}: {sorted(allowed) or 'none'}"
                )
                if wants_owner:
                    reason += "; owner change not applied either"
                skipped.append({"id": a.id, "reason": reason})
                continue
            _apply_status_change(db, a, body.status, actor=body.actor, note="bulk-update")
        if wants_owner:
            _log_event(
                db, a, event_type="reassigned",
                from_value=a.owner, to_value=body.owner,
                actor=body.actor, note="bulk-update",
            )
            a.owner = body.owner

        if wants_status or wants_owner:
            a.updated_at = datetime.utcnow()
            updated.append(a)
        else:
            skipped.append({"id": a.id, "reason": "no-op (already in requested state)"})
    db.commit()
    return BulkUpdateResponse(
        updated=[_to_response(a) for a in updated],
        missing=missing,
        skipped=skipped,
    )


@router.post("/sweep", response_model=SweepResponse)
def sla_sweep(db: Session = Depends(get_db)):
    """SLA breach sweep: escalate every active action past its deadline.

    Idempotent — already-escalated actions are not re-escalated; each breach
    writes one `sla_breach` audit event explaining how late the action was.
    In production this would run on a schedule; exposing it as an endpoint
    keeps the demo deterministic and inspectable.
    """
    now = datetime.utcnow()
    candidates = (
        db.query(Action)
        .filter(Action.status.in_(sorted(sla.ACTIVE_STATUSES)))
        .all()
    )
    escalated_ids: List[int] = []
    for a in candidates:
        if a.due_at is None or now <= a.due_at:
            continue
        overdue_minutes = -(sla.minutes_remaining(a, now) or 0)
        from_status = a.status
        a.status = "escalated"
        a.escalation_level = (a.escalation_level or 0) + 1
        a.updated_at = now
        _log_event(
            db, a, event_type="sla_breach",
            from_value=from_status, to_value="escalated",
            actor="sla-sweep",
            note=(
                f"SLA breached: {overdue_minutes} min past due "
                f"(window {a.sla_minutes} min for {a.source_category}/{a.urgency}); "
                f"escalation level {a.escalation_level}"
            ),
        )
        escalated_ids.append(a.id)
    db.commit()
    return SweepResponse(
        checked=len(candidates),
        breached=len(escalated_ids),
        escalated_ids=escalated_ids,
    )


@router.post("/{patient_id}", response_model=ActionResponse, status_code=201)
def create_action(patient_id: str, body: ActionCreate, db: Session = Depends(get_db)):
    if not db.query(Patient).filter(Patient.id == patient_id).first():
        raise HTTPException(404, f"patient {patient_id} not found")
    a = _new_action(patient_id, body.title, body.description, body.owner,
                    body.urgency, body.source_category)
    db.add(a)
    db.flush()
    _log_event(db, a, event_type="created", to_value="open", actor=body.actor)
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
            _check_transition(a.status, body.status)
            _apply_status_change(db, a, body.status, actor=body.actor)
    if body.owner is not None and body.owner != a.owner:
        _log_event(
            db, a, event_type="reassigned",
            from_value=a.owner, to_value=body.owner, actor=body.actor,
        )
        a.owner = body.owner
    a.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(a)
    return _to_response(a)


@router.post("/{action_id}/notes", response_model=ActionEventResponse, status_code=201)
def add_note(action_id: int, body: ActionNoteCreate, db: Session = Depends(get_db)):
    """Attach a free-text note to an action's audit trail."""
    a = db.query(Action).filter(Action.id == action_id).one_or_none()
    if not a:
        raise HTTPException(404, f"action {action_id} not found")
    ev = _log_event(db, a, event_type="note", actor=body.actor, note=body.note)
    a.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ev)
    return ActionEventResponse(
        id=ev.id, action_id=ev.action_id, event_type=ev.event_type,
        from_value=ev.from_value, to_value=ev.to_value,
        actor=ev.actor, note=ev.note, created_at=ev.created_at,
    )


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
