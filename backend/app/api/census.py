"""Census time-series + finalized handoff snapshots.

Gives the console memory of the floor over time: a real census/acuity trend
line for the analytics page, and immutable handoff artifacts you can retrieve
later ("the handoff given at 19:00 last night").

Operational coordination tooling, NOT a clinical decision aid.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.handoff import _shift_label, handoff as build_handoff
from app.db.database import get_db
from app.models.orm import HandoffSnapshot
from app.models.schemas import HandoffReport
from app.services import census as census_service


router = APIRouter(prefix="/census", tags=["census"])


class CensusPointOut(BaseModel):
    captured_at: datetime
    census: int
    red: int
    amber: int
    green: int
    open_actions: int
    overdue_actions: int
    silent_failures: int
    source: str


class CensusSeries(BaseModel):
    points: List[CensusPointOut]
    n: int


class CaptureResult(BaseModel):
    captured_at: datetime
    census: int
    red: int
    amber: int
    green: int


@router.get("/series", response_model=CensusSeries)
def get_series(limit: int = 200, db: Session = Depends(get_db)):
    """Census snapshots over time (oldest first) for sparklines/trend charts."""
    rows = census_service.census_series(db, limit=limit)
    points = [
        CensusPointOut(
            captured_at=r.captured_at,
            census=r.census,
            red=r.red,
            amber=r.amber,
            green=r.green,
            open_actions=r.open_actions,
            overdue_actions=r.overdue_actions,
            silent_failures=r.silent_failures,
            source=r.source,
        )
        for r in rows
    ]
    return CensusSeries(points=points, n=len(points))


@router.post("/snapshot", response_model=CaptureResult)
def take_snapshot(db: Session = Depends(get_db)):
    """Freeze a census snapshot now (the live tick does this automatically)."""
    snap = census_service.capture_census(db, source="manual")
    db.commit()
    return CaptureResult(
        captured_at=snap.captured_at, census=snap.census,
        red=snap.red, amber=snap.amber, green=snap.green,
    )


# ── Handoff snapshots ───────────────────────────────────────────────────


class HandoffSnapshotMeta(BaseModel):
    id: int
    captured_at: datetime
    shift_label: str
    finalized_by: str


class HandoffHistory(BaseModel):
    snapshots: List[HandoffSnapshotMeta]
    n: int


class FinalizeBody(BaseModel):
    finalized_by: str = "charge-rn"


@router.post("/handoff/finalize", response_model=HandoffSnapshotMeta)
def finalize_handoff(body: Optional[FinalizeBody] = None, db: Session = Depends(get_db)):
    """Freeze the CURRENT handoff report into an immutable artifact."""
    report: HandoffReport = build_handoff(db)
    payload = report.model_dump(mode="json")
    snap = census_service.finalize_handoff(
        db,
        report_payload=payload,
        shift_label=report.shift_label,
        finalized_by=(body.finalized_by if body else "charge-rn"),
    )
    db.commit()
    return HandoffSnapshotMeta(
        id=snap.id, captured_at=snap.captured_at,
        shift_label=snap.shift_label, finalized_by=snap.finalized_by,
    )


@router.get("/handoff/history", response_model=HandoffHistory)
def handoff_history(db: Session = Depends(get_db)):
    rows = census_service.handoff_history(db)
    metas = [
        HandoffSnapshotMeta(
            id=r.id, captured_at=r.captured_at,
            shift_label=r.shift_label, finalized_by=r.finalized_by,
        )
        for r in rows
    ]
    return HandoffHistory(snapshots=metas, n=len(metas))


@router.get("/handoff/{snapshot_id}", response_model=HandoffReport)
def get_handoff_snapshot(snapshot_id: int, db: Session = Depends(get_db)):
    """Retrieve a frozen handoff exactly as it was finalized."""
    snap = db.query(HandoffSnapshot).filter(HandoffSnapshot.id == snapshot_id).one_or_none()
    if not snap:
        raise HTTPException(404, f"Handoff snapshot {snapshot_id} not found")
    return HandoffReport(**snap.payload)
