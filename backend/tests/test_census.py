"""Tests for census time-series + finalized handoff snapshots."""

from __future__ import annotations

from app.main import app
from app.api.census import router as census_router
from tests.conftest import build_test_client, teardown_test_client


# Self-register the router if main.py hasn't (keeps the file runnable standalone).
if not any(getattr(r, "path", "").startswith("/census") for r in app.routes):
    app.include_router(census_router)


SEPSIS_NOTE = (
    "72yo with fever 39.4, BP 88/52, lactate 3.1, WBC 18. Meets SIRS. "
    "IV fluids 30 mL/kg initiated."
)
CLEAR_NOTE = (
    "38yo female, 2 days of dysuria. Afebrile. UA positive. "
    "Discharge home on nitrofurantoin."
)


def _client():
    return build_test_client(seed_patients=[
        {"id": "P-C001", "note_text": SEPSIS_NOTE, "truth_bottleneck": "missing_soc"},
        {"id": "P-C002", "note_text": CLEAR_NOTE, "truth_bottleneck": "clear"},
    ])


def test_snapshot_then_series():
    client, _ = _client()
    try:
        r = client.post("/census/snapshot")
        assert r.status_code == 200
        body = r.json()
        assert body["census"] == 2
        assert body["red"] >= 1  # sepsis patient is red

        s = client.get("/census/series")
        assert s.status_code == 200
        series = s.json()
        assert series["n"] >= 1
        assert series["points"][-1]["census"] == 2
        assert series["points"][-1]["source"] == "manual"
    finally:
        teardown_test_client()


def test_series_is_chronological():
    client, _ = _client()
    try:
        client.post("/census/snapshot")
        client.post("/census/snapshot")
        pts = client.get("/census/series").json()["points"]
        times = [p["captured_at"] for p in pts]
        assert times == sorted(times), "series must be oldest-first"
    finally:
        teardown_test_client()


def test_handoff_finalize_and_retrieve():
    client, _ = _client()
    try:
        f = client.post("/census/handoff/finalize", json={"finalized_by": "rn-jordan"})
        assert f.status_code == 200
        meta = f.json()
        assert meta["finalized_by"] == "rn-jordan"
        sid = meta["id"]

        hist = client.get("/census/handoff/history").json()
        assert hist["n"] >= 1
        assert any(h["id"] == sid for h in hist["snapshots"])

        # The frozen artifact is retrievable exactly as finalized.
        frozen = client.get(f"/census/handoff/{sid}")
        assert frozen.status_code == 200
        report = frozen.json()
        assert "shift_label" in report
        assert "critical" in report
        assert report["shift_label"] == meta["shift_label"]
    finally:
        teardown_test_client()


def test_handoff_snapshot_404():
    client, _ = _client()
    try:
        assert client.get("/census/handoff/99999").status_code == 404
    finally:
        teardown_test_client()


def test_handoff_snapshot_is_immutable():
    """A finalized handoff must not change when the live floor changes."""
    client, Session = _client()
    try:
        sid = client.post("/census/handoff/finalize").json()["id"]
        before = client.get(f"/census/handoff/{sid}").json()

        # Mutate the floor: discharge a patient directly.
        from app.models.orm import Patient
        db = Session()
        try:
            db.delete(db.get(Patient, "P-C002"))
            db.commit()
        finally:
            db.close()

        after = client.get(f"/census/handoff/{sid}").json()
        assert before == after, "frozen handoff must be immutable to later floor changes"
    finally:
        teardown_test_client()
