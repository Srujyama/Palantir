"""Shift handoff report.

Generates the artifact a charge RN hands the next shift: the list of patients
who matter, what's open, who owns what. Printable. Real hospital workflow.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, Patient, Triage
from app.models.schemas import HandoffReport, HandoffSection


router = APIRouter(prefix="/handoff", tags=["handoff"])


def _shift_label(now: datetime) -> str:
    """Compute a friendly shift label. Day shift 07-19, Night 19-07."""

    if 7 <= now.hour < 19:
        return f"Day shift handoff — {now.strftime('%a %d %b %H:%M')}"
    return f"Night shift handoff — {now.strftime('%a %d %b %H:%M')}"


def _patient_bullet(p: Patient, t: Triage) -> str:
    hrs = (datetime.utcnow() - p.arrival_time).total_seconds() / 3600
    return (
        f"Room {p.room} · {p.id} · {p.age}{p.sex} · "
        f"on floor {hrs:.0f}h · {p.chief_complaint}"
    )


@router.get("", response_model=HandoffReport)
def handoff(db: Session = Depends(get_db)):
    patients = db.query(Patient).all()
    by_id = {p.id: p for p in patients}
    triage = db.query(Triage).all()

    now = datetime.utcnow()

    critical_sections: List[HandoffSection] = []
    gap_sections: List[HandoffSection] = []
    dispo_sections: List[HandoffSection] = []

    for t in triage:
        p = by_id[t.patient_id]
        if t.primary_urgency == "red":
            critical_sections.append(
                HandoffSection(
                    title=f"{p.id} · {t.primary_label}",
                    patient_id=p.id,
                    room=p.room,
                    urgency="red",
                    bullets=[
                        _patient_bullet(p, t),
                        f"Action: {t.primary_action}",
                        f"Owner: {t.primary_owner or '—'}",
                        f"Rationale: {t.primary_rationale}",
                    ],
                )
            )
        if t.primary_category == "dispo_delay":
            dispo_sections.append(
                HandoffSection(
                    title=f"{p.id} · {t.primary_label}",
                    patient_id=p.id,
                    room=p.room,
                    urgency=t.primary_urgency,
                    bullets=[
                        _patient_bullet(p, t),
                        f"Hold: {t.primary_rationale}",
                        f"Action: {t.primary_action}",
                    ],
                )
            )
        for sf in t.payload.get("silent_failures", []):
            gap_sections.append(
                HandoffSection(
                    title=f"{p.id} · {sf['protocol_name']}",
                    patient_id=p.id,
                    room=p.room,
                    urgency=sf["urgency"],
                    bullets=[
                        _patient_bullet(p, t),
                        f"Missing: {sf['missing_action']}",
                        f"Citation: {sf['citation']}",
                        f"Owner: {sf['owner']}",
                    ],
                )
            )

    critical_sections.sort(key=lambda s: (s.room or "", s.patient_id or ""))
    gap_sections.sort(key=lambda s: (s.room or "", s.patient_id or ""))
    dispo_sections.sort(key=lambda s: (s.room or "", s.patient_id or ""))

    actions_by_owner: Dict[str, List[HandoffSection]] = defaultdict(list)
    open_actions = (
        db.query(Action)
        .filter(Action.status.in_(["open", "in_progress"]))
        .all()
    )
    for a in open_actions:
        p = by_id.get(a.patient_id)
        room = p.room if p else None
        actions_by_owner[a.owner or "—"].append(
            HandoffSection(
                title=f"#{a.id} · {a.title}",
                patient_id=a.patient_id,
                room=room,
                urgency=a.urgency,
                bullets=[
                    f"Patient: {a.patient_id} · room {room or '—'}",
                    f"Status: {a.status}",
                    f"Detail: {a.description}",
                ],
            )
        )
    for owner in actions_by_owner:
        actions_by_owner[owner].sort(key=lambda s: (s.urgency or "z", s.room or ""))

    summary = {
        "total_patients": len(patients),
        "critical": len(critical_sections),
        "open_gaps": len(gap_sections),
        "open_actions": len(open_actions),
        "dispo_holds": len(dispo_sections),
    }

    return HandoffReport(
        generated_at=now,
        shift_label=_shift_label(now),
        floor="Floors 3-5 · East and West wings",
        summary=summary,
        critical=critical_sections,
        open_protocol_gaps=gap_sections,
        awaiting_dispo=dispo_sections,
        open_actions_by_owner=dict(actions_by_owner),
    )
