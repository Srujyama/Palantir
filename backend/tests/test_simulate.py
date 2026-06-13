"""Tests for the demo-mode simulation tick endpoints (/simulate/*)."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.data.generate_notes import TEMPLATES
from app.main import app
from app.api.simulate import router as simulate_router
from tests.conftest import build_test_client, teardown_test_client


# The integrator wires the router into app.main; until then (and to keep this
# file self-contained either way) register it idempotently here.
if not any(getattr(r, "path", "") == "/simulate/tick" for r in app.routes):
    app.include_router(simulate_router)


CLEAR_UTI_NOTE = (
    "38yo female, 2 days of dysuria. Afebrile. UA positive. "
    "Discharge home on nitrofurantoin."
)
SEPSIS_NOTE = (
    "72yo with fever 39.4, BP 88/52, lactate 3.1, WBC 18. Meets SIRS. "
    "IV fluids 30 mL/kg initiated."
)
DISPO_NOTE = next(t for t in TEMPLATES if t.name == "copd_dispo_snf").note

SEED_ROOMS = {"3E-01", "3E-02", "3E-03"}


def _build_seeded_client():
    """3 patients (one dischargeable clear, one sepsis, one dispo) + 2 open
    actions created through the real API. Identical every call so ticks are
    reproducible."""
    base = datetime(2026, 6, 1, 8, 0, 0)
    client, TestingSession = build_test_client(
        seed_patients=[
            {
                "id": "P-9001",
                "note_text": CLEAR_UTI_NOTE,
                "chief_complaint": "Uncomplicated UTI",
                "arrival_time": base - timedelta(hours=30),
                "room": "3E-01",
            },
            {
                "id": "P-9002",
                "note_text": SEPSIS_NOTE,
                "chief_complaint": "Fever, hypotension",
                "arrival_time": base - timedelta(hours=8),
                "room": "3E-02",
            },
            {
                "id": "P-9003",
                "note_text": DISPO_NOTE,
                "chief_complaint": "COPD exacerbation, now resolved",
                "arrival_time": base - timedelta(hours=4),
                "room": "3E-03",
            },
        ]
    )
    for pid in ("P-9002", "P-9003"):
        r = client.post(
            f"/actions/{pid}",
            json={
                "title": f"Follow up {pid}",
                "description": "Created by simulate test",
                "owner": "physician",
                "urgency": "amber",
                "source_category": "missing_soc",
            },
        )
        assert r.status_code == 201
    return client, TestingSession


def test_status_before_tick():
    client, _ = _build_seeded_client()
    try:
        r = client.get("/simulate/status")
        assert r.status_code == 200
        body = r.json()
        assert body == {
            "census": 3,
            "beds_total": 180,
            "beds_free": 177,
            "open_actions": 2,
            "clear_patients": 1,
        }
    finally:
        teardown_test_client()


def test_tick_shape_discharge_admission_and_progression():
    client, _ = _build_seeded_client()
    try:
        # Sanity: the clear patient really classified clear and has no actions.
        rows = {p["id"]: p for p in client.get("/patients").json()}
        assert rows["P-9001"]["primary_category"] == "clear"
        assert rows["P-9001"]["open_actions"] == 0

        r = client.post("/simulate/tick", json={"minutes": 45})
        assert r.status_code == 200
        body = r.json()

        # Response shape
        assert set(body.keys()) == {
            "admitted", "discharged", "actions_progressed",
            "census_after", "tick_minutes",
        }
        assert body["tick_minutes"] == 45

        # Clear patient discharged, room recorded, gone from /patients.
        assert body["discharged"] == [{"patient_id": "P-9001", "room": "3E-01"}]
        assert client.get("/patients/P-9001").status_code == 404
        remaining_ids = {p["id"] for p in client.get("/patients").json()}
        assert "P-9001" not in remaining_ids

        # 1-2 admissions, IDs continue the sequence, rooms previously free.
        assert 1 <= len(body["admitted"]) <= 2
        for i, adm in enumerate(body["admitted"]):
            assert adm["patient_id"] == f"P-{9004 + i:04d}"
            assert adm["room"] not in SEED_ROOMS
            assert adm["category"]
            assert adm["urgency"] in {"red", "amber", "green"}
            assert adm["patient_id"] in remaining_ids
            detail = client.get(f"/patients/{adm['patient_id']}").json()
            assert detail["primary"]["category"] == adm["category"]

        # Census consistency: 3 seeded - 1 discharged + admitted.
        assert body["census_after"] == 3 - 1 + len(body["admitted"])
        assert body["census_after"] == len(remaining_ids)

        # Both open actions progressed open -> in_progress with audit events.
        assert len(body["actions_progressed"]) == 2
        for prog in body["actions_progressed"]:
            assert prog["from"] == "open"
            assert prog["to"] == "in_progress"
            events = client.get(f"/actions/{prog['action_id']}/events").json()
            assert any(
                e["event_type"] == "status_change"
                and e["actor"] == "sim-tick"
                and e["from_value"] == "open"
                and e["to_value"] == "in_progress"
                for e in events
            )

        # Second tick: those in_progress actions now resolve (oldest first).
        r2 = client.post("/simulate/tick", json={})
        assert r2.status_code == 200
        body2 = r2.json()
        assert body2["tick_minutes"] == 60  # default
        resolved = [
            p for p in body2["actions_progressed"]
            if p["from"] == "in_progress" and p["to"] == "resolved"
        ]
        assert len(resolved) == 2
    finally:
        teardown_test_client()


def test_tick_is_deterministic_for_identical_state():
    client_a, _ = _build_seeded_client()
    try:
        first = client_a.post("/simulate/tick", json={}).json()
    finally:
        teardown_test_client()

    client_b, _ = _build_seeded_client()
    try:
        second = client_b.post("/simulate/tick", json={}).json()
    finally:
        teardown_test_client()

    # Same state + same seed => byte-identical tick (ids, rooms, categories,
    # progression order — everything).
    assert first == second


# ---------------------------------------------------------------------------
# Regression: a discharged max-numbered patient's id must NOT be reissued to a
# new admit in the same tick (adversarial-review finding).
# ---------------------------------------------------------------------------

def test_tick_does_not_reissue_discharged_id():
    base = datetime(2026, 6, 1, 8, 0, 0)
    # The dischargeable clear patient is also the highest-numbered, so the naive
    # max-id scan (post-flush) would hand its id straight back.
    client, _ = build_test_client(
        seed_patients=[
            {"id": "P-1000", "note_text": SEPSIS_NOTE, "room": "3E-01",
             "arrival_time": base - timedelta(hours=8)},
            {"id": "P-1001", "note_text": CLEAR_UTI_NOTE, "room": "3E-02",
             "arrival_time": base - timedelta(hours=30)},
        ]
    )
    try:
        res = client.post("/simulate/tick", json={}).json()
        discharged = {d["patient_id"] for d in res["discharged"]}
        admitted = {a["patient_id"] for a in res["admitted"]}
        assert discharged, "expected the clear patient to be discharged"
        assert not (discharged & admitted), \
            f"reissued discharged id(s): {discharged & admitted}"
    finally:
        teardown_test_client()


def test_tick_does_not_discharge_patient_with_escalated_action():
    """An SLA-breached (escalated) action keeps its patient on the floor even if
    the triage is clear — otherwise the breach + audit trail get cascade-deleted."""
    from app.models.orm import Action, Patient

    base = datetime(2026, 6, 1, 8, 0, 0)
    client, Session = build_test_client(
        seed_patients=[
            {"id": "P-9100", "note_text": CLEAR_UTI_NOTE, "room": "3E-01",
             "arrival_time": base - timedelta(hours=30)},
        ]
    )
    try:
        a = client.post("/actions/P-9100", json={
            "title": "Pharmacy callback", "description": "x",
            "owner": "pharmacist", "urgency": "red", "source_category": "med_risk",
        }).json()
        # Backdate + sweep into escalated.
        db = Session()
        try:
            db.get(Action, a["id"]).due_at = base - timedelta(hours=99)
            db.commit()
        finally:
            db.close()
        sweep = client.post("/actions/sweep").json()
        assert sweep["breached"] >= 1
        client.post("/simulate/tick", json={})
        # Patient and the escalated action must both survive.
        assert client.get("/patients/P-9100").status_code == 200
        db = Session()
        try:
            assert db.get(Action, a["id"]) is not None
            assert db.get(Action, a["id"]).status == "escalated"
        finally:
            db.close()
    finally:
        teardown_test_client()
