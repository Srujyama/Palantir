"""Patient queue + detail endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.nlp.extractor import extract
from app.models.orm import Action, ActionEvent, NoteVersion, Patient, Triage
from app.models.schemas import (
    ActionResponse,
    BottleneckPayload,
    ICDCandidate,
    PatientDetail,
    PatientSummary,
    PatientTimeline,
    ProtocolMatchPayload,
    SilentFailurePayload,
    Span,
    TimelineEvent,
    TrendsPayload,
    WhyStuckResponse,
)
from app.services import sla


router = APIRouter(prefix="/patients", tags=["patients"])


URGENCY_ORDER = {"red": 0, "amber": 1, "green": 2}


def _open_actions_count(db: Session, patient_id: str) -> int:
    return (
        db.query(func.count(Action.id))
        .filter(Action.patient_id == patient_id, Action.status.in_(["open", "in_progress"]))
        .scalar()
        or 0
    )


def _overdue_actions_count(db: Session, patient_id: str, now: datetime) -> int:
    """Open / in-progress actions for this patient already past their SLA deadline."""
    return (
        db.query(func.count(Action.id))
        .filter(
            Action.patient_id == patient_id,
            Action.status.in_(["open", "in_progress"]),
            Action.due_at.isnot(None),
            Action.due_at < now,
        )
        .scalar()
        or 0
    )


def _silent_failure_count(triage: Triage) -> int:
    return len(triage.payload.get("silent_failures", []))


@router.get("", response_model=List[PatientSummary])
def list_patients(
    db: Session = Depends(get_db),
    urgency: Optional[str] = Query(None, pattern="^(red|amber|green)$"),
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
    now = datetime.utcnow()
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
                room=p.room,
                primary_category=t.primary_category,
                primary_label=t.primary_label,
                primary_urgency=t.primary_urgency,
                primary_owner=t.primary_owner,
                primary_action=t.primary_action,
                open_actions=_open_actions_count(db, p.id),
                overdue_actions=_overdue_actions_count(db, p.id, now),
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
        room=p.room,
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
                sla_minutes=a.sla_minutes, due_at=a.due_at,
                escalation_level=a.escalation_level or 0,
                overdue=sla.is_overdue(a), minutes_remaining=sla.minutes_remaining(a),
                created_at=a.created_at, updated_at=a.updated_at,
            )
            for a in sorted(p.actions, key=lambda a: a.created_at, reverse=True)
        ],
        trends=TrendsPayload(**t.trends) if t.trends else None,
    )


@router.get("/{patient_id}/timeline", response_model=PatientTimeline)
def patient_timeline(patient_id: str, db: Session = Depends(get_db)):
    """Builds an ordered timeline of events for this patient: arrival, triage,
    each gap detected, each action lifecycle event. Used by the timeline view
    on the patient detail page."""

    p = db.query(Patient).filter(Patient.id == patient_id).one_or_none()
    if not p:
        raise HTTPException(404, f"Patient {patient_id} not found")
    payload = p.triage.payload

    events: List[TimelineEvent] = []

    # Prior notes (clinical history) come before arrival on the timeline.
    priors = (
        db.query(NoteVersion)
        .filter(NoteVersion.patient_id == patient_id)
        .order_by(NoteVersion.sequence)
        .all()
    )
    for nv in priors:
        # Digest each prior note's OWN labs (not the current values).
        prior_labs = extract(nv.note_text).labs
        seen: set[str] = set()
        parts: List[str] = []
        for f in prior_labs:
            if f.label in seen or f.value is None:
                continue
            seen.add(f.label)
            parts.append(f"{f.label} {f.value}")
        digest = " · ".join(parts[:5])
        events.append(
            TimelineEvent(
                timestamp=nv.captured_at,
                kind="prior_note",
                title=f"Prior note — {nv.hours_ago}h ago",
                detail=digest[:160] if digest else "Earlier documented state",
                actor="chart",
            )
        )

    events.append(
        TimelineEvent(
            timestamp=p.arrival_time,
            kind="arrival",
            title=f"Arrived on floor — {p.chief_complaint}",
            detail=f"Room {p.room or 'unassigned'} · {p.age}{p.sex}",
        ),
    )
    events.append(
        TimelineEvent(
            timestamp=p.triage.computed_at,
            kind="triage",
            title="Pipeline ran on note",
            detail=f"{payload['primary']['label']} ({payload['primary']['urgency']})",
            urgency=payload["primary"]["urgency"],
            actor="pipeline",
        ),
    )
    for sf in payload.get("silent_failures", []):
        events.append(
            TimelineEvent(
                timestamp=p.triage.computed_at,
                kind="gap_detected",
                title=f"Gap surfaced: {sf['missing_action']}",
                detail=f"{sf['protocol_name']} · {sf['citation']}",
                urgency=sf["urgency"],
                actor="pipeline",
            )
        )
    actions = (
        db.query(Action)
        .filter(Action.patient_id == patient_id)
        .order_by(Action.created_at.asc())
        .all()
    )
    for a in actions:
        events.append(
            TimelineEvent(
                timestamp=a.created_at,
                kind="action_created",
                title=f"Action opened: {a.title}",
                detail=f"Owner: {a.owner} · {a.description[:120]}",
                urgency=a.urgency,
                actor="charge-rn",
            )
        )
        for ev in a.events:
            events.append(
                TimelineEvent(
                    timestamp=ev.created_at,
                    kind="action_state",
                    title=f"Action #{a.id}: {ev.event_type.replace('_', ' ')}",
                    detail=f"{ev.from_value or '—'} → {ev.to_value or '—'}",
                    actor=ev.actor,
                )
            )

    events.sort(key=lambda e: e.timestamp)
    return PatientTimeline(patient_id=p.id, events=events)


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
