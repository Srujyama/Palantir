"""Bed-capacity forecast + what-if simulation endpoints.

Thin HTTP layer over app/services/capacity.py: the deterministic residual-LOS
model that projects when beds free up and what resolving specific bottlenecks
would buy. Every response carries the assumptions that produced it — this is
an operational coordination tool, NOT a clinical decision aid.

Response models live in this module (not app/models/schemas.py) because they
are private to the capacity surface.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.orm import Patient
from app.services.capacity import BASE_RESIDUAL_HOURS, forecast, simulate


router = APIRouter(prefix="/capacity", tags=["capacity"])


# ---------------------------------------------------------------------------
# Response / request models (local to this surface)
# ---------------------------------------------------------------------------

class CensusPoint(BaseModel):
    hour_offset: int
    projected_census: int
    projected_discharges_cum: int
    projected_admissions_cum: int
    projected_free: int


class WingSnapshot(BaseModel):
    wing: str
    beds_total: int
    occupied: int
    free: int
    projected_discharges_24h: int


class Assumption(BaseModel):
    key: str
    label: str
    value: str
    rationale: str


class ForecastResponse(BaseModel):
    anchor: datetime
    horizon_hours: int
    beds_total: int
    census_now: int
    series: List[CensusPoint]
    wings: List[WingSnapshot]
    assumptions: List[Assumption]


class SimulateRequest(BaseModel):
    resolve_categories: List[str] = Field(default_factory=list)
    resolve_patient_ids: List[str] = Field(default_factory=list)
    horizon_hours: int = Field(48, ge=1, le=168)


class FreedPatient(BaseModel):
    patient_id: str
    room: Optional[str] = None
    category: str
    urgency: str
    baseline_eta_hours: int
    scenario_eta_hours: int
    gained_hours: int


class SimulateResponse(BaseModel):
    anchor: datetime
    horizon_hours: int
    beds_total: int
    baseline: List[CensusPoint]
    scenario: List[CensusPoint]
    freed: List[FreedPatient]
    delta_free_beds: Dict[str, int]
    assumptions: List[Assumption]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/forecast", response_model=ForecastResponse)
def capacity_forecast(
    horizon: int = Query(48, ge=1, le=168, description="Forecast horizon in hours"),
    db: Session = Depends(get_db),
):
    """Hourly bed-capacity forecast with per-wing snapshot and assumptions."""
    return forecast(db, horizon_hours=horizon)


@router.post("/simulate", response_model=SimulateResponse)
def capacity_simulate(req: SimulateRequest, db: Session = Depends(get_db)):
    """What-if: resolve bottlenecks by category and/or patient id, re-forecast.

    Rejects unknown category names AND unknown patient ids rather than silently
    matching nothing — a typo'd scenario should fail loudly, not look like a
    null result.
    """
    unknown = sorted(set(req.resolve_categories) - set(BASE_RESIDUAL_HOURS))
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unknown bottleneck categories: {', '.join(unknown)}. "
                f"Valid: {', '.join(sorted(BASE_RESIDUAL_HOURS))}"
            ),
        )
    if req.resolve_patient_ids:
        existing = {
            pid
            for (pid,) in db.query(Patient.id)
            .filter(Patient.id.in_(req.resolve_patient_ids))
            .all()
        }
        unknown_ids = sorted(set(req.resolve_patient_ids) - existing)
        if unknown_ids:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown patient ids: {', '.join(unknown_ids)}",
            )
    return simulate(
        db,
        resolve_categories=req.resolve_categories,
        resolve_patient_ids=req.resolve_patient_ids,
        horizon_hours=req.horizon_hours,
    )
