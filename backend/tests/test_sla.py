"""Tests for the SLA policy table and the action lifecycle engine.

Covers: policy lookup, due_at stamping on create, the status state machine
(valid + invalid transitions), the notes endpoint, overdue computation on
GET /actions, the SLA sweep (escalation + audit event + idempotency), the
bulk-patch missing/skipped report, and the per-patient overdue count.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.orm import Action
from app.services import sla
from tests.conftest import build_test_client, teardown_test_client


CLEAR_NOTE = (
    "38yo female, 2 days of dysuria. Afebrile. UA positive. "
    "Discharge home on nitrofurantoin."
)


@pytest.fixture()
def ctx():
    client, Session = build_test_client(seed_patients=[
        {"id": "P-S001", "note_text": CLEAR_NOTE},
        {"id": "P-S002", "note_text": CLEAR_NOTE},
    ])
    yield client, Session
    teardown_test_client()


def _create_action(client, patient_id="P-S001", **overrides):
    body = {
        "title": "Test action",
        "description": "Test description",
        "owner": "physician",
        "urgency": "red",
        "source_category": "missing_soc",
    }
    body.update(overrides)
    r = client.post(f"/actions/{patient_id}", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _backdate(Session, action_id: int, minutes: int = 120) -> None:
    """Push an action's deadline into the past directly in the DB."""
    db = Session()
    try:
        a = db.get(Action, action_id)
        a.due_at = datetime.utcnow() - timedelta(minutes=minutes)
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Policy table
# ---------------------------------------------------------------------------

def test_sla_policy_lookup():
    assert sla.sla_minutes_for("missing_soc", "red") == 60
    assert sla.sla_minutes_for("missing_soc", "amber") == 240
    assert sla.sla_minutes_for("med_risk", "red") == 60
    assert sla.sla_minutes_for("med_risk", "amber") == 120
    # Wildcard categories apply regardless of urgency
    assert sla.sla_minutes_for("awaiting_consult", "red") == 240
    assert sla.sla_minutes_for("awaiting_consult", "amber") == 240
    assert sla.sla_minutes_for("awaiting_imaging", "amber") == 180
    assert sla.sla_minutes_for("readmit_risk", "amber") == 720
    assert sla.sla_minutes_for("dispo_delay", "green") == 1440
    # Unknown category falls back to the default shift window
    assert sla.sla_minutes_for("queue_bulk", "green") == sla.DEFAULT_SLA_MINUTES
    assert sla.sla_minutes_for("missing_soc", "green") == sla.DEFAULT_SLA_MINUTES


def test_compute_due_at():
    created = datetime(2026, 6, 12, 8, 0, 0)
    due = sla.compute_due_at(created, "missing_soc", "red")
    assert due == created + timedelta(minutes=60)
    due = sla.compute_due_at(created, "dispo_delay", "green")
    assert due == created + timedelta(minutes=1440)


# ---------------------------------------------------------------------------
# Create stamps SLA fields
# ---------------------------------------------------------------------------

def test_create_sets_due_at(ctx):
    client, _ = ctx
    a = _create_action(client, source_category="missing_soc", urgency="red")
    assert a["sla_minutes"] == 60
    assert a["due_at"] is not None
    created = datetime.fromisoformat(a["created_at"])
    due = datetime.fromisoformat(a["due_at"])
    assert due - created == timedelta(minutes=60)
    assert a["escalation_level"] == 0
    assert a["overdue"] is False
    assert a["minutes_remaining"] is not None
    assert 0 < a["minutes_remaining"] <= 60


def test_bulk_create_sets_due_at(ctx):
    client, _ = ctx
    r = client.post("/actions/bulk", json={
        "patient_ids": ["P-S001", "P-S002"],
        "title": "Bulk", "description": "Bulk",
        "owner": "case_manager", "urgency": "green",
        "source_category": "dispo_delay",
    })
    assert r.status_code == 201
    for a in r.json():
        assert a["sla_minutes"] == 1440
        assert a["due_at"] is not None
        assert a["overdue"] is False


def test_create_validates_owner_and_urgency(ctx):
    client, _ = ctx
    base = {
        "title": "x", "description": "x",
        "owner": "physician", "urgency": "red",
        "source_category": "missing_soc",
    }
    r = client.post("/actions/P-S001", json={**base, "owner": "janitor"})
    assert r.status_code == 422
    r = client.post("/actions/P-S001", json={**base, "urgency": "purple"})
    assert r.status_code == 422
    r = client.post("/actions/bulk", json={
        **base, "patient_ids": ["P-S001"], "owner": "janitor",
    })
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

def test_state_machine_valid_transitions(ctx):
    client, _ = ctx
    aid = _create_action(client)["id"]
    # open -> in_progress -> open -> in_progress -> resolved -> open (reopen)
    for target in ["in_progress", "open", "in_progress", "resolved", "open"]:
        r = client.patch(f"/actions/{aid}", json={"status": target})
        assert r.status_code == 200, r.text
        assert r.json()["status"] == target
    # open -> escalated bumps escalation_level; escalated -> in_progress allowed
    r = client.patch(f"/actions/{aid}", json={"status": "escalated"})
    assert r.status_code == 200
    assert r.json()["escalation_level"] == 1
    r = client.patch(f"/actions/{aid}", json={"status": "in_progress"})
    assert r.status_code == 200


def test_state_machine_invalid_transition_422(ctx):
    client, _ = ctx
    aid = _create_action(client)["id"]
    r = client.patch(f"/actions/{aid}", json={"status": "resolved"})
    assert r.status_code == 200
    # resolved -> in_progress is illegal; only reopen (-> open) is allowed
    r = client.patch(f"/actions/{aid}", json={"status": "in_progress"})
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "resolved -> in_progress" in detail
    assert "open" in detail  # message lists allowed transitions
    # escalated -> open is illegal
    r = client.patch(f"/actions/{aid}", json={"status": "open"})
    assert r.status_code == 200
    r = client.patch(f"/actions/{aid}", json={"status": "escalated"})
    assert r.status_code == 200
    r = client.patch(f"/actions/{aid}", json={"status": "open"})
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# Notes + actor threading
# ---------------------------------------------------------------------------

def test_notes_endpoint(ctx):
    client, _ = ctx
    aid = _create_action(client)["id"]
    r = client.post(f"/actions/{aid}/notes", json={
        "note": "Paged cardiology again", "actor": "night-charge",
    })
    assert r.status_code == 201
    ev = r.json()
    assert ev["event_type"] == "note"
    assert ev["actor"] == "night-charge"
    assert ev["note"] == "Paged cardiology again"

    events = client.get(f"/actions/{aid}/events").json()
    notes = [e for e in events if e["event_type"] == "note"]
    assert len(notes) == 1
    assert notes[0]["actor"] == "night-charge"

    r = client.post("/actions/999999/notes", json={"note": "ghost"})
    assert r.status_code == 404


def test_actor_threaded_on_create_and_update(ctx):
    client, _ = ctx
    aid = _create_action(client, actor="unit-clerk")["id"]
    client.patch(f"/actions/{aid}", json={"status": "in_progress", "actor": "rn-day"})
    events = client.get(f"/actions/{aid}/events").json()
    by_type = {e["event_type"]: e for e in events}
    assert by_type["created"]["actor"] == "unit-clerk"
    assert by_type["status_change"]["actor"] == "rn-day"


# ---------------------------------------------------------------------------
# GET /actions overdue computation + sorting
# ---------------------------------------------------------------------------

def test_list_actions_overdue(ctx):
    client, Session = ctx
    late = _create_action(client, title="late one")
    fresh = _create_action(client, title="fresh one", patient_id="P-S002")
    _backdate(Session, late["id"], minutes=90)

    rows = client.get("/actions").json()
    by_id = {r["id"]: r for r in rows}
    assert by_id[late["id"]]["overdue"] is True
    assert by_id[late["id"]]["minutes_remaining"] < 0
    assert by_id[fresh["id"]]["overdue"] is False
    # Overdue rows sort first
    assert rows[0]["id"] == late["id"]
    # patient_id is on every row
    assert by_id[late["id"]]["patient_id"] == "P-S001"

    only_overdue = client.get("/actions?overdue=true").json()
    assert [r["id"] for r in only_overdue] == [late["id"]]
    not_overdue = client.get("/actions?overdue=false").json()
    assert late["id"] not in {r["id"] for r in not_overdue}


def test_resolved_actions_are_not_overdue(ctx):
    client, Session = ctx
    a = _create_action(client)
    client.patch(f"/actions/{a['id']}", json={"status": "resolved"})
    _backdate(Session, a["id"], minutes=90)
    rows = client.get("/actions").json()
    row = next(r for r in rows if r["id"] == a["id"])
    assert row["overdue"] is False


# ---------------------------------------------------------------------------
# SLA sweep
# ---------------------------------------------------------------------------

def test_sweep_escalates_and_is_idempotent(ctx):
    client, Session = ctx
    late = _create_action(client, title="breached")
    fresh = _create_action(client, title="on time", patient_id="P-S002")
    _backdate(Session, late["id"], minutes=45)

    r = client.post("/actions/sweep")
    assert r.status_code == 200
    body = r.json()
    assert body["checked"] >= 2
    assert body["breached"] == 1
    assert body["escalated_ids"] == [late["id"]]

    row = next(x for x in client.get("/actions").json() if x["id"] == late["id"])
    assert row["status"] == "escalated"
    assert row["escalation_level"] == 1

    events = client.get(f"/actions/{late['id']}/events").json()
    breaches = [e for e in events if e["event_type"] == "sla_breach"]
    assert len(breaches) == 1
    assert breaches[0]["actor"] == "sla-sweep"
    assert "SLA breached" in breaches[0]["note"]
    assert "45" in breaches[0]["note"] or "46" in breaches[0]["note"]

    # Second sweep skips already-escalated actions
    r2 = client.post("/actions/sweep")
    body2 = r2.json()
    assert body2["breached"] == 0
    assert body2["escalated_ids"] == []
    row = next(x for x in client.get("/actions").json() if x["id"] == late["id"])
    assert row["escalation_level"] == 1
    events = client.get(f"/actions/{late['id']}/events").json()
    assert len([e for e in events if e["event_type"] == "sla_breach"]) == 1

    # The fresh action was untouched
    row = next(x for x in client.get("/actions").json() if x["id"] == fresh["id"])
    assert row["status"] == "open"


# ---------------------------------------------------------------------------
# Bulk patch report
# ---------------------------------------------------------------------------

def test_bulk_patch_reports_missing_ids(ctx):
    client, _ = ctx
    a = _create_action(client)
    r = client.patch("/actions/bulk", json={
        "action_ids": [a["id"], 999999],
        "status": "in_progress",
    })
    assert r.status_code == 200
    body = r.json()
    assert [x["id"] for x in body["updated"]] == [a["id"]]
    assert body["updated"][0]["status"] == "in_progress"
    assert body["missing"] == [999999]
    assert body["skipped"] == []


def test_bulk_patch_reports_skipped_invalid_transitions(ctx):
    client, _ = ctx
    a = _create_action(client)
    b = _create_action(client, patient_id="P-S002")
    client.patch(f"/actions/{a['id']}", json={"status": "resolved"})
    r = client.patch("/actions/bulk", json={
        "action_ids": [a["id"], b["id"]],
        "status": "in_progress",
    })
    assert r.status_code == 200
    body = r.json()
    assert [x["id"] for x in body["updated"]] == [b["id"]]
    assert len(body["skipped"]) == 1
    assert body["skipped"][0]["id"] == a["id"]
    assert "resolved -> in_progress" in body["skipped"][0]["reason"]


# ---------------------------------------------------------------------------
# Patient list overdue count
# ---------------------------------------------------------------------------

def test_patient_list_overdue_actions_count(ctx):
    client, Session = ctx
    a1 = _create_action(client, patient_id="P-S002", title="will breach")
    _create_action(client, patient_id="P-S002", title="on track")
    _backdate(Session, a1["id"], minutes=30)

    rows = client.get("/patients").json()
    row = next(r for r in rows if r["id"] == "P-S002")
    assert row["open_actions"] == 2
    assert row["overdue_actions"] == 1
    clean = next(r for r in rows if r["id"] == "P-S001")
    assert clean["overdue_actions"] == 0


# ---------------------------------------------------------------------------
# Regression: PATCH owner validation + bulk partial-failure semantics
# (adversarial-review findings)
# ---------------------------------------------------------------------------

def test_patch_rejects_bogus_owner(ctx):
    client, _ = ctx
    a = _create_action(client)
    r = client.patch(f"/actions/{a['id']}", json={"owner": "totally-bogus-owner"})
    assert r.status_code == 422
    # empty string also rejected
    assert client.patch(f"/actions/{a['id']}", json={"owner": ""}).status_code == 422


def test_bulk_patch_rejects_bogus_owner(ctx):
    client, _ = ctx
    a = _create_action(client)
    r = client.patch("/actions/bulk", json={"action_ids": [a["id"]], "owner": "nope"})
    assert r.status_code == 422


def test_bulk_patch_skip_reports_dropped_owner_change(ctx):
    client, _ = ctx
    a = _create_action(client)
    # Drive to resolved so in_progress is an illegal transition.
    client.patch(f"/actions/{a['id']}", json={"status": "in_progress"})
    client.patch(f"/actions/{a['id']}", json={"status": "resolved"})
    r = client.patch("/actions/bulk", json={
        "action_ids": [a["id"]], "status": "in_progress", "owner": "case_manager",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["updated"] == []
    assert len(body["skipped"]) == 1
    assert "owner change not applied" in body["skipped"][0]["reason"]


def test_bulk_patch_dedups_and_reports_noops(ctx):
    client, _ = ctx
    a = _create_action(client, owner="physician")
    # Duplicate ids, requesting the owner it already has -> one no-op skip.
    r = client.patch("/actions/bulk", json={
        "action_ids": [a["id"], a["id"]], "owner": "physician",
    })
    body = r.json()
    assert body["updated"] == []
    assert [s["id"] for s in body["skipped"]] == [a["id"]]
    assert "no-op" in body["skipped"][0]["reason"]
