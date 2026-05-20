"""Floor map endpoint.

Renders the spatial state of the floor: every bed, who's in it, what the
primary bottleneck is. Charge nurses use the wall board for this in real
hospitals; the map is the digital version.
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, Patient, Triage
from app.models.schemas import FloorBed, FloorMap


router = APIRouter(prefix="/floor", tags=["floor"])


WINGS = ["3E", "3W", "4E", "4W", "5E", "5W"]
BEDS_PER_WING = 30


@router.get("", response_model=FloorMap)
def floor_map(db: Session = Depends(get_db)):
    patients = db.query(Patient).all()
    by_room: Dict[str, Patient] = {p.room: p for p in patients if p.room}

    open_count_by_pid: Dict[str, int] = dict(
        db.query(Action.patient_id, func.count(Action.id))
        .filter(Action.status.in_(["open", "in_progress"]))
        .group_by(Action.patient_id)
        .all()
    )

    beds: List[FloorBed] = []
    for wing in WINGS:
        for n in range(1, BEDS_PER_WING + 1):
            room = f"{wing}-{n:02d}"
            p = by_room.get(room)
            if p:
                t = p.triage
                beds.append(
                    FloorBed(
                        room=room,
                        wing=wing,
                        bed_number=n,
                        patient_id=p.id,
                        urgency=t.primary_urgency if t else None,
                        primary_category=t.primary_category if t else None,
                        primary_owner=t.primary_owner if t else None,
                        chief_complaint=p.chief_complaint,
                        age=p.age,
                        sex=p.sex,
                        open_actions=open_count_by_pid.get(p.id, 0),
                    )
                )
            else:
                beds.append(
                    FloorBed(room=room, wing=wing, bed_number=n)
                )

    return FloorMap(wings=WINGS, beds_per_wing=BEDS_PER_WING, beds=beds)
