"""Tests for the bed-capacity forecast and what-if simulator.

The capacity router is registered here (guarded) because app/main.py wiring
is owned by the integrator; once main.py includes the router the guard makes
this a no-op.
"""

from __future__ import annotations

import pytest

from app.main import app
from app.api.capacity import router as capacity_router
from tests.conftest import build_test_client, teardown_test_client


# Register the capacity router if main.py has not done so yet.
if not any(getattr(r, "path", "").startswith("/capacity") for r in app.routes):
    app.include_router(capacity_router)


BEDS_TOTAL = 180
SEEDED = 5

SEED_PATIENTS = [
    {
        # dispo_delay (green, owner case_manager)
        "id": "P-CAP-01",
        "chief_complaint": "Placement hold",
        "note_text": (
            "Medically ready for discharge. SNF placement pending insurance "
            "authorization. Case management following."
        ),
    },
    {
        # missing_soc (red) — sepsis trigger with no antibiotics documented
        "id": "P-CAP-02",
        "age": 80,  # also exercises the age >= 75 modifier
        "chief_complaint": "Fever, hypotension",
        "note_text": (
            "80yo with fever 39.4, BP 88/52, lactate 3.1, WBC 18. Meets SIRS. "
            "IV fluids 30 mL/kg initiated."
        ),
    },
    {
        # awaiting_imaging (amber)
        "id": "P-CAP-03",
        "chief_complaint": "Abdominal pain",
        "note_text": (
            "Abdominal pain, stable vitals. CT abd pending, in queue. "
            "Disposition decision awaiting imaging."
        ),
    },
    {
        # awaiting_consult (amber, owner physician)
        "id": "P-CAP-04",
        "chief_complaint": "Hip fracture",
        "note_text": (
            "Hip fracture, surgical candidate. Orthopedic consult requested "
            "14h ago, awaiting callback. Patient otherwise medically optimized."
        ),
    },
    {
        # clear (green)
        "id": "P-CAP-05",
        "chief_complaint": "Uncomplicated UTI",
        "note_text": (
            "38yo female, 2 days of dysuria. Afebrile. UA positive. "
            "Discharge home on nitrofurantoin."
        ),
    },
]


@pytest.fixture(scope="module")
def client():
    c, _ = build_test_client(seed_patients=SEED_PATIENTS)
    yield c
    teardown_test_client()


def test_seed_categories(client):
    """Sanity: the engineered notes triage into the categories we rely on."""
    rows = client.get("/patients").json()
    by_id = {r["id"]: r["primary_category"] for r in rows}
    assert by_id["P-CAP-01"] == "dispo_delay"
    assert by_id["P-CAP-02"] == "missing_soc"
    assert by_id["P-CAP-03"] == "awaiting_imaging"
    assert by_id["P-CAP-04"] == "awaiting_consult"
    assert by_id["P-CAP-05"] == "clear"


def test_forecast_starts_at_seeded_census(client):
    r = client.get("/capacity/forecast")
    assert r.status_code == 200
    body = r.json()
    assert body["beds_total"] == BEDS_TOTAL
    assert body["census_now"] == SEEDED
    first = body["series"][0]
    assert first["hour_offset"] == 0
    assert first["projected_census"] == SEEDED
    assert first["projected_discharges_cum"] == 0
    assert first["projected_admissions_cum"] == 0
    assert first["projected_free"] == BEDS_TOTAL - SEEDED


def test_forecast_series_is_monotonic_sane(client):
    body = client.get("/capacity/forecast?horizon=48").json()
    series = body["series"]
    assert len(series) == 49  # hour 0..48 inclusive
    prev_d, prev_a = 0, 0
    for pt in series:
        assert 0 <= pt["projected_free"] <= BEDS_TOTAL
        assert 0 <= pt["projected_census"] <= BEDS_TOTAL
        assert pt["projected_census"] + pt["projected_free"] == BEDS_TOTAL
        assert pt["projected_discharges_cum"] >= prev_d
        assert pt["projected_admissions_cum"] >= prev_a
        prev_d = pt["projected_discharges_cum"]
        prev_a = pt["projected_admissions_cum"]
    # The clear / imaging / consult patients (residual <= 30h + window
    # rounding slack <= 12h) always discharge inside 48h; dispo (48h) and
    # missing_soc (60h) can roll past the horizon at night anchors.
    assert series[-1]["projected_discharges_cum"] >= 3


def test_forecast_wings_and_assumptions(client):
    body = client.get("/capacity/forecast").json()
    wings = body["wings"]
    assert len(wings) == 6
    assert sum(w["occupied"] for w in wings) == SEEDED
    e3 = next(w for w in wings if w["wing"] == "3E")
    assert e3["occupied"] == SEEDED  # conftest rooms patients in 3E
    assert e3["free"] == 30 - SEEDED

    assumptions = body["assumptions"]
    assert len(assumptions) > 0
    for a in assumptions:
        assert a["key"] and a["label"] and a["value"] and a["rationale"]
    keys = {a["key"] for a in assumptions}
    assert "base_residual_hours" in keys
    assert "discharge_window" in keys
    assert "resolution_benefit_hours" in keys


def test_simulate_resolving_dispo_frees_beds(client):
    r = client.post("/capacity/simulate", json={"resolve_categories": ["dispo_delay"]})
    assert r.status_code == 200
    body = r.json()

    baseline = body["baseline"]
    scenario = body["scenario"]
    assert len(baseline) == len(scenario) == 49

    # Resolving a bottleneck can never make capacity worse.
    for b, s in zip(baseline, scenario):
        assert s["projected_free"] >= b["projected_free"]

    # The dispo patient leaves 36h earlier — a bed frees up by 24h or 48h.
    delta = body["delta_free_beds"]
    assert set(delta) == {"6h", "12h", "24h", "48h"}
    assert delta["24h"] > 0 or delta["48h"] > 0

    freed = body["freed"]
    dispo = [f for f in freed if f["patient_id"] == "P-CAP-01"]
    assert len(dispo) == 1
    assert dispo[0]["category"] == "dispo_delay"
    assert dispo[0]["gained_hours"] > 0
    assert dispo[0]["scenario_eta_hours"] < dispo[0]["baseline_eta_hours"]

    assert len(body["assumptions"]) > 0


def test_simulate_by_patient_id(client):
    # Target the missing_soc patient: its 18h resolution benefit always
    # survives discharge-window rounding (benefits <= 12h can be absorbed
    # by the roll-forward to 08:00 at some anchor hours).
    r = client.post(
        "/capacity/simulate",
        json={"resolve_patient_ids": ["P-CAP-02"]},
    )
    assert r.status_code == 200
    freed = r.json()["freed"]
    assert [f["patient_id"] for f in freed] == ["P-CAP-02"]
    assert freed[0]["category"] == "missing_soc"
    assert freed[0]["gained_hours"] > 0
    assert freed[0]["scenario_eta_hours"] <= freed[0]["baseline_eta_hours"]


def test_simulate_rejects_unknown_category(client):
    r = client.post("/capacity/simulate", json={"resolve_categories": ["dispo_dleay"]})
    assert r.status_code == 422


def test_simulate_rejects_unknown_patient_id(client):
    """A typo'd patient id should fail loudly, not look like a null result."""
    r = client.post("/capacity/simulate", json={"resolve_patient_ids": ["P-9999", "NOPE"]})
    assert r.status_code == 422
    assert "P-9999" in r.json()["detail"]


def test_simulate_freed_rows_are_strictly_earlier(client):
    """Every freed patient must discharge strictly earlier than baseline —
    no gained_hours == 0 rows absorbed by the discharge window."""
    r = client.post("/capacity/simulate", json={"resolve_categories": ["dispo_delay"]})
    body = r.json()
    assert body["freed"], "dispo_delay scenario should free beds"
    for f in body["freed"]:
        assert f["gained_hours"] > 0
        assert f["scenario_eta_hours"] < f["baseline_eta_hours"]


def test_forecast_deterministic(client):
    a = client.get("/capacity/forecast?horizon=24").json()
    b = client.get("/capacity/forecast?horizon=24").json()
    assert a == b


def test_simulate_deterministic(client):
    payload = {"resolve_categories": ["dispo_delay", "awaiting_imaging"], "horizon_hours": 48}
    a = client.post("/capacity/simulate", json=payload).json()
    b = client.post("/capacity/simulate", json=payload).json()
    assert a == b
