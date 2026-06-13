"""Bed-capacity forecast + what-if scenario simulation.

A deterministic residual length-of-stay (LOS) model over the current census:
every patient gets a projected discharge time derived from a small table of
stated assumptions (base residual hours by bottleneck category, urgency and
age modifiers, a discharge window), and projected admissions come from the
observed hourly arrival pattern in the corpus. The "what-if" simulator
re-runs the same model with the blocking bottleneck resolved and reports the
beds that free up and when.

There is NO randomness and NO ML here — every number in the output traces to
an assumption that is itself returned in the response (`assumptions`), so a
charge nurse or bed manager can audit the whole projection. This is an
operational coordination tool, NOT a clinical decision aid: it forecasts bed
availability, it does not advise on care.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.orm import Patient


# ---------------------------------------------------------------------------
# Model knobs. Everything below is a stated assumption, surfaced verbatim in
# the `assumptions` block of every response.
# ---------------------------------------------------------------------------

# Mirrors the floor geometry declared in app/api/floor.py (WINGS x
# BEDS_PER_WING). Re-declared locally so this service has no dependency on
# API-layer internals; keep the two in sync.
WINGS: List[str] = ["3E", "3W", "4E", "4W", "5E", "5W"]
BEDS_PER_WING: int = 30
BEDS_TOTAL: int = len(WINGS) * BEDS_PER_WING  # 180

# Expected remaining hours on the floor given the primary bottleneck.
BASE_RESIDUAL_HOURS: Dict[str, int] = {
    "clear": 6,
    "awaiting_imaging": 18,
    "awaiting_consult": 24,
    "readmit_risk": 24,
    "med_risk": 36,
    "missing_soc": 36,
    "dispo_delay": 48,
}

# Hours saved if the blocking bottleneck is resolved right now.
RESOLUTION_BENEFIT_HOURS: Dict[str, int] = {
    "clear": 0,
    "awaiting_imaging": 10,
    "awaiting_consult": 14,
    "med_risk": 18,
    "missing_soc": 18,
    "dispo_delay": 36,
    "readmit_risk": 8,
}

# Sicker patients stay longer regardless of category.
URGENCY_MODIFIER_HOURS: Dict[str, int] = {"red": 12, "amber": 6, "green": 0}

# Older patients need more discharge coordination.
AGE_MODIFIER_THRESHOLD: int = 75
AGE_MODIFIER_HOURS: int = 12

# Discharges only complete between these local hours (inclusive start,
# exclusive end). Projections falling outside roll forward to the next 08:00.
DISCHARGE_WINDOW_START: int = 8
DISCHARGE_WINDOW_END: int = 20

# A resolved patient still needs paperwork, transport, and a final exam.
MIN_SCENARIO_RESIDUAL_HOURS: int = 4

# Offsets at which simulate() reports the freed-bed delta.
DELTA_CHECKPOINT_HOURS: List[int] = [6, 12, 24, 48]


@dataclass
class PatientProjection:
    """One patient's projected discharge under a given set of resolutions."""

    patient_id: str
    room: Optional[str]
    category: str
    urgency: str
    age: int
    residual_hours: int           # modified residual before window rounding
    discharge_offset_hours: int   # hours after the anchor, window-rounded


# ---------------------------------------------------------------------------
# Core mechanics
# ---------------------------------------------------------------------------

def _anchor(now: Optional[datetime] = None) -> datetime:
    """Forecast anchor: the top of the current hour (UTC).

    Truncating to the hour makes the model deterministic — two calls within
    the same hour produce byte-identical output.
    """
    base = now or datetime.utcnow()
    return base.replace(minute=0, second=0, microsecond=0)


def _round_to_discharge_window(dt: datetime) -> datetime:
    """Roll a projected discharge forward to the next in-window hour."""
    if DISCHARGE_WINDOW_START <= dt.hour < DISCHARGE_WINDOW_END:
        return dt
    if dt.hour >= DISCHARGE_WINDOW_END:
        dt = dt + timedelta(days=1)
    return dt.replace(hour=DISCHARGE_WINDOW_START, minute=0, second=0, microsecond=0)


def _residual_hours(category: str, urgency: str, age: int) -> int:
    """Modified residual LOS: base by category + urgency + age modifiers."""
    base = BASE_RESIDUAL_HOURS.get(category, BASE_RESIDUAL_HOURS["clear"])
    base += URGENCY_MODIFIER_HOURS.get(urgency, 0)
    if age >= AGE_MODIFIER_THRESHOLD:
        base += AGE_MODIFIER_HOURS
    return base


def _project_patients(
    patients: List[Patient],
    anchor: datetime,
    resolve_categories: Optional[List[str]] = None,
    resolve_patient_ids: Optional[List[str]] = None,
) -> List[PatientProjection]:
    """Project a discharge time for every patient on the floor.

    Patients whose primary bottleneck category is in `resolve_categories`,
    or whose id is in `resolve_patient_ids`, get the scenario residual:
    max(MIN_SCENARIO_RESIDUAL_HOURS, modified residual - resolution benefit).
    """
    cats = set(resolve_categories or [])
    pids = set(resolve_patient_ids or [])

    projections: List[PatientProjection] = []
    for p in sorted(patients, key=lambda x: x.id):
        triage = p.triage
        category = triage.primary_category if triage else "clear"
        urgency = triage.primary_urgency if triage else "green"

        residual = _residual_hours(category, urgency, p.age)
        if category in cats or p.id in pids:
            benefit = RESOLUTION_BENEFIT_HOURS.get(category, 0)
            residual = max(MIN_SCENARIO_RESIDUAL_HOURS, residual - benefit)

        discharge_at = _round_to_discharge_window(anchor + timedelta(hours=residual))
        offset = int((discharge_at - anchor).total_seconds() // 3600)
        projections.append(
            PatientProjection(
                patient_id=p.id,
                room=p.room,
                category=category,
                urgency=urgency,
                age=p.age,
                residual_hours=residual,
                discharge_offset_hours=offset,
            )
        )
    return projections


def _arrival_rate_by_hour(patients: List[Patient]) -> Dict[int, float]:
    """Mean arrivals per hour-of-day, computed from Patient.arrival_time.

    rate[h] = (# arrivals whose arrival hour == h) / (# distinct arrival
    dates in the corpus). Purely descriptive of the seeded corpus — no
    smoothing, no fitting.
    """
    counts: Dict[int, int] = {h: 0 for h in range(24)}
    dates = set()
    for p in patients:
        counts[p.arrival_time.hour] += 1
        dates.add(p.arrival_time.date())
    days = max(1, len(dates))
    return {h: counts[h] / days for h in range(24)}


def _build_series(
    census_now: int,
    projections: List[PatientProjection],
    rates: Dict[int, float],
    anchor: datetime,
    horizon_hours: int,
) -> List[Dict]:
    """Hourly census series over the horizon.

    census(h) = census_now + cumulative admissions - cumulative discharges,
    clamped to [0, BEDS_TOTAL] (arrivals beyond capacity divert; the floor
    cannot go negative). Admissions accumulate as the floor of the running
    expected-arrival total so the series stays integer and monotone.
    """
    discharge_offsets = sorted(p.discharge_offset_hours for p in projections)
    series: List[Dict] = []
    cum_rate = 0.0
    discharged = 0
    for h in range(horizon_hours + 1):
        if h > 0:
            cum_rate += rates[(anchor.hour + h) % 24]
        while discharged < len(discharge_offsets) and discharge_offsets[discharged] <= h:
            discharged += 1
        admissions_cum = int(cum_rate)
        census = census_now + admissions_cum - discharged
        census = max(0, min(BEDS_TOTAL, census))
        series.append(
            {
                "hour_offset": h,
                "projected_census": census,
                "projected_discharges_cum": discharged,
                "projected_admissions_cum": admissions_cum,
                "projected_free": BEDS_TOTAL - census,
            }
        )
    return series


def _wing_snapshot(
    patients: List[Patient],
    projections: List[PatientProjection],
    horizon_hours: int,
) -> List[Dict]:
    """Current per-wing occupancy plus discharges projected inside 24h."""
    cutoff = min(24, horizon_hours)
    occupied: Dict[str, int] = {w: 0 for w in WINGS}
    discharging: Dict[str, int] = {w: 0 for w in WINGS}

    proj_by_pid = {p.patient_id: p for p in projections}
    for p in patients:
        if not p.room or "-" not in p.room:
            continue
        wing = p.room.split("-")[0]
        if wing not in occupied:
            continue
        occupied[wing] += 1
        proj = proj_by_pid.get(p.id)
        if proj and proj.discharge_offset_hours <= cutoff:
            discharging[wing] += 1

    return [
        {
            "wing": w,
            "beds_total": BEDS_PER_WING,
            "occupied": occupied[w],
            "free": BEDS_PER_WING - occupied[w],
            "projected_discharges_24h": discharging[w],
        }
        for w in WINGS
    ]


def _fmt_table(table: Dict[str, int]) -> str:
    return ", ".join(f"{k}={v}" for k, v in sorted(table.items(), key=lambda kv: kv[1]))


def _assumptions(anchor: datetime, n_patients: int, n_days: int) -> List[Dict]:
    """The model's knobs, stated in full. Every output number traces here."""
    return [
        {
            "key": "base_residual_hours",
            "label": "Base residual LOS by bottleneck category",
            "value": _fmt_table(BASE_RESIDUAL_HOURS),
            "rationale": (
                "Expected remaining hours on the floor given what is blocking "
                "the patient; fixed planning constants, not clinical predictions."
            ),
        },
        {
            "key": "urgency_modifier_hours",
            "label": "Urgency modifier",
            "value": "red=+12h, amber=+6h, green=+0h",
            "rationale": "Higher-acuity patients need more stabilization time before discharge.",
        },
        {
            "key": "age_modifier_hours",
            "label": "Age modifier",
            "value": f"age >= {AGE_MODIFIER_THRESHOLD} adds +{AGE_MODIFIER_HOURS}h",
            "rationale": "Older patients need more discharge coordination (placement, transport, family).",
        },
        {
            "key": "discharge_window",
            "label": "Discharge window",
            "value": (
                f"{DISCHARGE_WINDOW_START:02d}:00-{DISCHARGE_WINDOW_END:02d}:00; "
                "out-of-window discharges roll forward to the next 08:00"
            ),
            "rationale": "Floors do not discharge overnight; staffing and transport stop at 20:00.",
        },
        {
            "key": "resolution_benefit_hours",
            "label": "Hours saved if the blocking bottleneck resolves",
            "value": _fmt_table(RESOLUTION_BENEFIT_HOURS),
            "rationale": (
                "Per-category estimate of the wait embedded in the residual; "
                "subtracted in what-if scenarios."
            ),
        },
        {
            "key": "min_scenario_residual_hours",
            "label": "Minimum residual after resolution",
            "value": f"{MIN_SCENARIO_RESIDUAL_HOURS}h",
            "rationale": "Paperwork, final exam, and transport take time even with nothing blocking.",
        },
        {
            "key": "beds_total",
            "label": "Total bed capacity",
            "value": f"{BEDS_TOTAL} ({len(WINGS)} wings x {BEDS_PER_WING} beds)",
            "rationale": "Mirrors the floor geometry in the floor map (app/api/floor.py).",
        },
        {
            "key": "arrival_rate",
            "label": "Projected admissions",
            "value": (
                f"mean arrivals per hour-of-day over {n_patients} corpus "
                f"arrivals across {n_days} distinct day(s)"
            ),
            "rationale": (
                "Hourly arrival counts from Patient.arrival_time divided by days "
                "observed; applied over the horizon and floored to whole patients."
            ),
        },
        {
            "key": "anchor",
            "label": "Forecast anchor",
            "value": anchor.isoformat(),
            "rationale": "Top of the current hour (UTC); keeps repeated calls deterministic.",
        },
        {
            "key": "census_clamp",
            "label": "Census bounds",
            "value": f"census clamped to [0, {BEDS_TOTAL}]",
            "rationale": "Arrivals beyond capacity divert elsewhere; occupancy cannot go negative.",
        },
    ]


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------

def forecast(db: Session, horizon_hours: int = 48) -> Dict:
    """Bed-capacity forecast over `horizon_hours`.

    Returns the hourly census series, a per-wing snapshot, and the full
    assumptions list that produced every number.
    """
    patients = db.query(Patient).all()
    anchor = _anchor()
    rates = _arrival_rate_by_hour(patients)
    projections = _project_patients(patients, anchor)
    n_days = max(1, len({p.arrival_time.date() for p in patients}))

    return {
        "anchor": anchor,
        "horizon_hours": horizon_hours,
        "beds_total": BEDS_TOTAL,
        "census_now": len(patients),
        "series": _build_series(len(patients), projections, rates, anchor, horizon_hours),
        "wings": _wing_snapshot(patients, projections, horizon_hours),
        "assumptions": _assumptions(anchor, len(patients), n_days),
    }


def simulate(
    db: Session,
    resolve_categories: Optional[List[str]] = None,
    resolve_patient_ids: Optional[List[str]] = None,
    horizon_hours: int = 48,
) -> Dict:
    """What-if simulation: resolve a set of bottlenecks, re-run the model.

    Patients whose primary bottleneck category is in `resolve_categories`
    (or whose id is in `resolve_patient_ids`) get the scenario residual.
    Returns baseline and scenario series, the per-patient beds freed, and
    the free-bed delta at fixed checkpoints.
    """
    resolve_categories = resolve_categories or []
    resolve_patient_ids = resolve_patient_ids or []

    patients = db.query(Patient).all()
    anchor = _anchor()
    rates = _arrival_rate_by_hour(patients)
    n_days = max(1, len({p.arrival_time.date() for p in patients}))

    baseline_proj = _project_patients(patients, anchor)
    scenario_proj = _project_patients(
        patients, anchor,
        resolve_categories=resolve_categories,
        resolve_patient_ids=resolve_patient_ids,
    )

    baseline = _build_series(len(patients), baseline_proj, rates, anchor, horizon_hours)
    scenario = _build_series(len(patients), scenario_proj, rates, anchor, horizon_hours)

    scenario_by_pid = {p.patient_id: p for p in scenario_proj}
    freed: List[Dict] = []
    for bp in baseline_proj:
        sp = scenario_by_pid[bp.patient_id]
        # "Freed" means the bed comes back strictly earlier. A patient whose
        # residual shrank but whose discharge still rounds to the same in-window
        # hour (benefit absorbed by the 08:00-20:00 discharge window) gains zero
        # real beds and is not reported — the readout stays honest.
        if sp.discharge_offset_hours >= bp.discharge_offset_hours:
            continue
        freed.append(
            {
                "patient_id": bp.patient_id,
                "room": bp.room,
                "category": bp.category,
                "urgency": bp.urgency,
                "baseline_eta_hours": bp.discharge_offset_hours,
                "scenario_eta_hours": sp.discharge_offset_hours,
                "gained_hours": bp.discharge_offset_hours - sp.discharge_offset_hours,
            }
        )
    freed.sort(key=lambda f: (-f["gained_hours"], f["patient_id"]))

    delta_free_beds = {
        f"{h}h": scenario[h]["projected_free"] - baseline[h]["projected_free"]
        for h in DELTA_CHECKPOINT_HOURS
        if h <= horizon_hours
    }

    return {
        "anchor": anchor,
        "horizon_hours": horizon_hours,
        "beds_total": BEDS_TOTAL,
        "baseline": baseline,
        "scenario": scenario,
        "freed": freed,
        "delta_free_beds": delta_free_beds,
        "assumptions": _assumptions(anchor, len(patients), n_days),
    }
