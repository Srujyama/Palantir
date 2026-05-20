"""Integration tests against the FastAPI surface.

Uses a fresh in-memory SQLite DB per test session so we don't clobber the
real app.db.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.database as db_module
from app.main import app
from app.db.database import Base, get_db
from app.models.orm import Action, ActionEvent, Patient  # noqa: F401  (register)
from app.services.pipeline import run as run_pipeline


@pytest.fixture(scope="module")
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        try:
            db = TestingSession()
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed two synthetic patients
    from datetime import datetime, timedelta
    db = TestingSession()
    try:
        p1 = Patient(
            id="P-T001", age=72, sex="F",
            chief_complaint="Fever, hypotension",
            note_text=(
                "72yo with fever 39.4, BP 88/52, lactate 3.1, WBC 18. Meets SIRS. "
                "IV fluids 30 mL/kg initiated."
            ),
            arrival_time=datetime.utcnow() - timedelta(hours=8),
            template_name="sepsis_no_abx",
            truth_bottleneck="missing_soc",
            room="3E-01",
        )
        p2 = Patient(
            id="P-T002", age=38, sex="F",
            chief_complaint="Uncomplicated UTI",
            note_text=(
                "38yo female, 2 days of dysuria. Afebrile. UA positive. "
                "Discharge home on nitrofurantoin."
            ),
            arrival_time=datetime.utcnow() - timedelta(hours=2),
            template_name="clear_uti",
            truth_bottleneck="clear",
            room="3E-02",
        )
        db.add(p1)
        db.add(p2)
        db.flush()
        run_pipeline(db, p1)
        run_pipeline(db, p2)
        db.commit()
    finally:
        db.close()

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_patients(client):
    r = client.get("/patients")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    ids = {r["id"] for r in rows}
    assert {"P-T001", "P-T002"} == ids


def test_filter_by_urgency(client):
    r = client.get("/patients?urgency=red")
    assert r.status_code == 200
    rows = r.json()
    assert all(r["primary_urgency"] == "red" for r in rows)


def test_patient_detail(client):
    r = client.get("/patients/P-T001")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "P-T001"
    assert body["room"] == "3E-01"
    assert "primary" in body
    assert "silent_failures" in body
    # sepsis bundle should fire
    assert body["primary"]["category"] == "missing_soc"


def test_why_stuck(client):
    r = client.get("/patients/P-T001/why")
    assert r.status_code == 200
    body = r.json()
    assert body["patient_id"] == "P-T001"
    assert len(body["bullet_points"]) > 0


def test_timeline(client):
    r = client.get("/patients/P-T001/timeline")
    assert r.status_code == 200
    body = r.json()
    assert body["patient_id"] == "P-T001"
    kinds = {e["kind"] for e in body["events"]}
    # At minimum arrival and triage should exist
    assert "arrival" in kinds
    assert "triage" in kinds


def test_floor_map(client):
    r = client.get("/floor")
    assert r.status_code == 200
    body = r.json()
    assert len(body["beds"]) == 6 * 30
    occupied = [b for b in body["beds"] if b["patient_id"]]
    assert len(occupied) == 2


def test_analytics(client):
    r = client.get("/analytics")
    assert r.status_code == 200
    body = r.json()
    assert body["total_patients"] == 2
    assert "by_urgency" in body
    assert "by_protocol" in body


def test_handoff(client):
    r = client.get("/handoff")
    assert r.status_code == 200
    body = r.json()
    assert "shift_label" in body
    assert isinstance(body["critical"], list)


def test_create_and_list_action(client):
    r = client.post("/actions/P-T001", json={
        "title": "Page surgery",
        "description": "Confirm OR slot",
        "owner": "physician",
        "urgency": "amber",
        "source_category": "awaiting_consult",
    })
    assert r.status_code == 201
    action = r.json()
    assert action["status"] == "open"
    aid = action["id"]

    # Events
    r2 = client.get(f"/actions/{aid}/events")
    assert r2.status_code == 200
    events = r2.json()
    assert any(e["event_type"] == "created" for e in events)


def test_action_state_change_logs_event(client):
    r = client.post("/actions/P-T002", json={
        "title": "Discharge teaching",
        "description": "Confirm meds",
        "owner": "nurse",
        "urgency": "green",
        "source_category": "clear",
    })
    aid = r.json()["id"]
    r2 = client.patch(f"/actions/{aid}", json={"status": "in_progress"})
    assert r2.status_code == 200
    r3 = client.patch(f"/actions/{aid}", json={"status": "resolved"})
    assert r3.status_code == 200

    events = client.get(f"/actions/{aid}/events").json()
    types = [e["event_type"] for e in events]
    assert types.count("status_change") == 2


def test_bulk_create_actions(client):
    r = client.post("/actions/bulk", json={
        "patient_ids": ["P-T001", "P-T002"],
        "title": "Owner sync",
        "description": "Routed via bulk",
        "owner": "case_manager",
        "urgency": "green",
        "source_category": "queue_bulk",
    })
    assert r.status_code == 201
    actions = r.json()
    assert len(actions) == 2
    # Each must have a "bulk-created" event
    for a in actions:
        events = client.get(f"/actions/{a['id']}/events").json()
        assert any(e.get("note") == "bulk-created" for e in events)


def test_bulk_create_404_on_missing_patient(client):
    r = client.post("/actions/bulk", json={
        "patient_ids": ["P-T001", "P-DOES-NOT-EXIST"],
        "title": "x", "description": "x",
        "owner": "physician", "urgency": "amber", "source_category": "x",
    })
    assert r.status_code == 404
