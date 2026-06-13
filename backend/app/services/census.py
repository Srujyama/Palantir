"""Census time-series + handoff snapshots.

Two small persistence helpers that give the console memory:

- `capture_census` freezes a floor-wide roll-up (occupancy, acuity mix, open
  and overdue actions, silent-failure count) so analytics can draw a real
  trend line instead of a single snapshot.
- `finalize_handoff` freezes a handoff report into an immutable artifact you
  can retrieve later — the auditable record a live dashboard cannot be.

Operational coordination tooling, NOT a clinical decision aid.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.orm import Action, CensusSnapshot, HandoffSnapshot, Patient, Triage


def _roll_up(db: Session) -> Dict[str, int]:
    """Compute the current floor roll-up from live rows."""
    now = datetime.utcnow()
    triages = db.query(Triage).all()
    by_urg = {"red": 0, "amber": 0, "green": 0}
    silent = 0
    for t in triages:
        by_urg[t.primary_urgency] = by_urg.get(t.primary_urgency, 0) + 1
        silent += len(t.payload.get("silent_failures", []))

    census = db.query(func.count(Patient.id)).scalar() or 0
    open_actions = (
        db.query(func.count(Action.id))
        .filter(Action.status.in_(["open", "in_progress"]))
        .scalar()
        or 0
    )
    overdue = (
        db.query(func.count(Action.id))
        .filter(
            Action.status.in_(["open", "in_progress"]),
            Action.due_at.isnot(None),
            Action.due_at < now,
        )
        .scalar()
        or 0
    )
    return {
        "census": census,
        "red": by_urg["red"],
        "amber": by_urg["amber"],
        "green": by_urg["green"],
        "open_actions": open_actions,
        "overdue_actions": overdue,
        "silent_failures": silent,
    }


def capture_census(db: Session, source: str = "manual") -> CensusSnapshot:
    """Freeze a census snapshot. Caller commits."""
    roll = _roll_up(db)
    snap = CensusSnapshot(captured_at=datetime.utcnow(), source=source, **roll)
    db.add(snap)
    db.flush()
    return snap


def census_series(db: Session, limit: int = 200) -> List[CensusSnapshot]:
    """Most-recent-last census snapshots for sparklines."""
    rows = (
        db.query(CensusSnapshot)
        .order_by(CensusSnapshot.captured_at.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


def finalize_handoff(
    db: Session, report_payload: Dict, shift_label: str, finalized_by: str = "charge-rn"
) -> HandoffSnapshot:
    """Freeze a handoff report into an immutable artifact. Caller commits."""
    snap = HandoffSnapshot(
        captured_at=datetime.utcnow(),
        shift_label=shift_label,
        finalized_by=finalized_by,
        payload=report_payload,
    )
    db.add(snap)
    db.flush()
    return snap


def handoff_history(db: Session, limit: int = 50) -> List[HandoffSnapshot]:
    return (
        db.query(HandoffSnapshot)
        .order_by(HandoffSnapshot.captured_at.desc())
        .limit(limit)
        .all()
    )
