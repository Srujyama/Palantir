"""KPI stats endpoint for the dashboard strip."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from statistics import median

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Action, Patient, Triage
from app.models.schemas import StatsResponse


router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsResponse)
def stats(db: Session = Depends(get_db)):
    triage_rows = db.query(Triage).all()
    patients = db.query(Patient).all()
    by_pid = {p.id: p for p in patients}

    by_urgency = Counter(t.primary_urgency for t in triage_rows)
    by_category = Counter(t.primary_label for t in triage_rows)
    by_owner = Counter(t.primary_owner or "—" for t in triage_rows)
    silent = sum(len(t.payload.get("silent_failures", [])) for t in triage_rows)
    open_actions = (
        db.query(func.count(Action.id))
        .filter(Action.status.in_(["open", "in_progress"]))
        .scalar()
        or 0
    )
    now = datetime.utcnow()
    ages = [(now - by_pid[t.patient_id].arrival_time).total_seconds() / 3600 for t in triage_rows]
    median_age = round(median(ages), 1) if ages else 0.0

    return StatsResponse(
        total_patients=len(patients),
        by_urgency=dict(by_urgency),
        by_category=dict(by_category),
        by_owner=dict(by_owner),
        open_actions=open_actions,
        silent_failures=silent,
        median_arrival_age_hours=median_age,
    )
