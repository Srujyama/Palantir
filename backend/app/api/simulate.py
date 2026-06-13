"""Demo-mode "living floor" simulation tick.

POST /simulate/tick advances the operational state one step so the console
visibly moves during a demo: ready-for-discharge patients leave, new arrivals
come in through the exact same deterministic triage pipeline as a real
ingest, and the oldest open actions progress through their workflow.

Everything is seeded from the current DB state — random.Random(seed) with
seed = patient_count * 1000 + action_count — so a given floor state always
produces the same tick. No LLM calls, no hidden state: every admitted
patient's triage is rule-based and citation-backed, and every action change
writes an audit ActionEvent. This is an operational coordination demo aid,
NOT a clinical decision aid.
"""

from __future__ import annotations

import random
import re
from datetime import datetime
from typing import List, Optional, Set, Tuple

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.data.generate_notes import TEMPLATES, Template
from app.db.database import get_db
from app.models.orm import Action, ActionEvent, Patient, Triage
from app.services.pipeline import run as run_pipeline


router = APIRouter(prefix="/simulate", tags=["simulate"])


# Floor layout — mirrors the 6 wings x 30 beds grid rendered by /floor.
# Re-declared locally so this module has no dependency on the floor router.
WINGS = ["3E", "3W", "4E", "4W", "5E", "5W"]
BEDS_PER_WING = 30

# Per-tick movement caps. Small on purpose: the demo should drift, not churn.
MAX_DISCHARGES_PER_TICK = 2
MAX_OPEN_TO_IN_PROGRESS = 3
MAX_IN_PROGRESS_TO_RESOLVED = 2

SIM_ACTOR = "sim-tick"

_PATIENT_ID_RE = re.compile(r"^P-(\d+)$")

# Templates whose presentation depends on biological sex (mirrors the
# generation machinery in app.data.generate_notes).
_SEX_LOCKED = {"rlq_pain_awaiting_ct"}


# ---------------------------------------------------------------------------
# Response / request models (kept local — schemas.py is owned elsewhere)
# ---------------------------------------------------------------------------

class TickRequest(BaseModel):
    """How much simulated wall-clock time this tick represents."""

    minutes: int = Field(default=60, ge=1, le=24 * 60)


class AdmittedPatient(BaseModel):
    patient_id: str
    room: str
    category: str
    urgency: str


class DischargedPatient(BaseModel):
    patient_id: str
    room: Optional[str] = None


class ActionProgress(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action_id: int
    from_status: str = Field(alias="from")
    to_status: str = Field(alias="to")


class TickResponse(BaseModel):
    admitted: List[AdmittedPatient]
    discharged: List[DischargedPatient]
    actions_progressed: List[ActionProgress]
    census_after: int
    tick_minutes: int


class SimStatus(BaseModel):
    census: int
    beds_total: int
    beds_free: int
    open_actions: int
    clear_patients: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_patient_ids(db: Session, count: int) -> List[str]:
    """Continue the P-XXXX sequence above the current numeric max."""
    max_n = 999
    for (pid,) in db.query(Patient.id).all():
        m = _PATIENT_ID_RE.match(pid)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return [f"P-{max_n + i + 1:04d}" for i in range(count)]


def _occupied_rooms(db: Session) -> Set[str]:
    return {
        room
        for (room,) in db.query(Patient.room).filter(Patient.room.isnot(None)).all()
    }


def _free_rooms(occupied: Set[str]) -> List[str]:
    """All free beds in wing order (3E-01, 3E-02, … 5W-30)."""
    rooms: List[str] = []
    for wing in WINGS:
        for n in range(1, BEDS_PER_WING + 1):
            room = f"{wing}-{n:02d}"
            if room not in occupied:
                rooms.append(room)
    return rooms


def _vary_template(tmpl: Template, rng: random.Random) -> Tuple[int, str]:
    """Derive (age, sex) for a new admit from a note template.

    Mirrors the variation rules in app.data.generate_notes.generate(): pull
    the seed age out of the note text (first "##yo" token), jitter it, and
    occasionally flip sex when not pathognomonic. The note text itself is
    used verbatim from the template so the extractor sees the same signals.
    """
    base_age = 50
    for tok in tmpl.note.split():
        if tok.endswith("yo") and tok[:-2].isdigit():
            base_age = int(tok[:-2])
            break
    age = max(18, base_age + rng.randint(-4, 4))

    sex = "F" if "female" in tmpl.note.lower() else "M"
    if tmpl.name not in _SEX_LOCKED and rng.random() < 0.15:
        sex = "M" if sex == "F" else "F"
    return age, sex


def _progress_action(
    db: Session, action: Action, to_status: str, now: datetime
) -> ActionProgress:
    """Move one action forward and write the audit ActionEvent."""
    from_status = action.status
    db.add(
        ActionEvent(
            action_id=action.id,
            event_type="status_change",
            from_value=from_status,
            to_value=to_status,
            actor=SIM_ACTOR,
            note="simulation tick",
        )
    )
    action.status = to_status
    action.updated_at = now
    return ActionProgress(action_id=action.id, from_status=from_status, to_status=to_status)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/tick", response_model=TickResponse)
def tick(body: Optional[TickRequest] = None, db: Session = Depends(get_db)):
    """Advance the floor one simulated step.

    Deterministic by construction: the RNG is seeded from the current state
    (patient count * 1000 + total action count), so replaying the same state
    always yields the same admissions, discharges and progressions.
    """
    minutes = body.minutes if body else 60

    patient_count = db.query(func.count(Patient.id)).scalar() or 0
    action_count = db.query(func.count(Action.id)).scalar() or 0
    rng = random.Random(patient_count * 1000 + action_count)

    # Snapshot rooms and the ID sequence *before* discharging, so beds freed
    # this tick are not instantly reused (housekeeping turnover — they come
    # free next tick) and discharged IDs are never reissued. The ID scan must
    # run here, before db.flush() applies the deletes, or a just-discharged
    # max-numbered patient's ID would be handed straight back to a new admit.
    occupied_before = _occupied_rooms(db)
    free_rooms = _free_rooms(occupied_before)
    n_admits = rng.randint(1, 2)
    new_ids = _next_patient_ids(db, n_admits)

    # -- DISCHARGES: clear patients with no outstanding work, oldest first.
    #    "escalated" counts as outstanding — an SLA-breached action is the most
    #    important unresolved work on the floor; discharging its patient would
    #    cascade-delete the breach and its audit trail.
    blocked_ids = {
        pid
        for (pid,) in db.query(Action.patient_id)
        .filter(Action.status.in_(("open", "in_progress", "escalated")))
        .distinct()
        .all()
    }
    clear_rows = (
        db.query(Patient)
        .join(Triage)
        .filter(Triage.primary_category == "clear")
        .order_by(Patient.arrival_time.asc(), Patient.id.asc())
        .all()
    )
    discharged: List[DischargedPatient] = []
    for p in clear_rows:
        if len(discharged) >= MAX_DISCHARGES_PER_TICK:
            break
        if p.id in blocked_ids:
            continue
        discharged.append(DischargedPatient(patient_id=p.id, room=p.room))
        db.delete(p)  # ORM cascade removes triage + actions (+ their events)
    db.flush()

    # -- ADMISSIONS: 1-2 new arrivals minted from the note templates, run
    #    through the same triage pipeline as a real ingest. (n_admits and
    #    new_ids were computed above, before the discharge flush.)
    admitted: List[AdmittedPatient] = []
    now = datetime.utcnow()
    for i in range(n_admits):
        if not free_rooms:
            break  # floor is full; admissions wait for the next tick
        tmpl = rng.choice(TEMPLATES)
        age, sex = _vary_template(tmpl, rng)
        room = free_rooms.pop(0)
        patient = Patient(
            id=new_ids[i],
            age=age,
            sex=sex,
            chief_complaint=tmpl.chief_complaint,
            note_text=tmpl.note,
            arrival_time=now,
            template_name=tmpl.name,
            truth_bottleneck=tmpl.truth_bottleneck,
            room=room,
        )
        db.add(patient)
        db.flush()
        triage = run_pipeline(db, patient)
        db.flush()
        admitted.append(
            AdmittedPatient(
                patient_id=patient.id,
                room=room,
                category=triage.primary_category,
                urgency=triage.primary_urgency,
            )
        )

    # -- PROGRESSION: snapshot both queues first so an action moved to
    #    in_progress this tick cannot also resolve this tick.
    open_rows = (
        db.query(Action)
        .filter(Action.status == "open")
        .order_by(Action.created_at.asc(), Action.id.asc())
        .limit(MAX_OPEN_TO_IN_PROGRESS)
        .all()
    )
    in_progress_rows = (
        db.query(Action)
        .filter(Action.status == "in_progress")
        .order_by(Action.created_at.asc(), Action.id.asc())
        .limit(MAX_IN_PROGRESS_TO_RESOLVED)
        .all()
    )
    progressed: List[ActionProgress] = [
        _progress_action(db, a, "in_progress", now) for a in open_rows
    ] + [
        _progress_action(db, a, "resolved", now) for a in in_progress_rows
    ]

    db.commit()
    census_after = db.query(func.count(Patient.id)).scalar() or 0

    return TickResponse(
        admitted=admitted,
        discharged=discharged,
        actions_progressed=progressed,
        census_after=census_after,
        tick_minutes=minutes,
    )


@router.get("/status", response_model=SimStatus)
def simulate_status(db: Session = Depends(get_db)):
    """Cheap dashboard for the demo driver: census, free beds, open work."""
    census = db.query(func.count(Patient.id)).scalar() or 0
    beds_total = len(WINGS) * BEDS_PER_WING
    occupied = (
        db.query(func.count(func.distinct(Patient.room)))
        .filter(Patient.room.isnot(None))
        .scalar()
        or 0
    )
    open_actions = (
        db.query(func.count(Action.id))
        .filter(Action.status.in_(("open", "in_progress")))
        .scalar()
        or 0
    )
    clear_patients = (
        db.query(func.count(Patient.id))
        .join(Triage)
        .filter(Triage.primary_category == "clear")
        .scalar()
        or 0
    )
    return SimStatus(
        census=census,
        beds_total=beds_total,
        beds_free=beds_total - occupied,
        open_actions=open_actions,
        clear_patients=clear_patients,
    )
