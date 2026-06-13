"""Tests for the triage sandbox endpoints and the evaluation harness.

The seeded eval cohort is engineered: three notes the classifier should get
right (sepsis missing_soc, awaiting_imaging, clear) and one deliberate miss
(truth med_risk, note carries no detectable interaction signals) so the
summary math, confusion cells, and /eval/misses output are all exercised
exactly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.main import app
from app.api.evaluation import router as evaluation_router
from app.api.sandbox import router as sandbox_router
from app.nlp.extractor import extract
from app.services.bottleneck import classify
from tests.conftest import build_test_client, teardown_test_client


NOTES_PATH = Path(__file__).parent.parent / "app" / "data" / "patient_notes.json"

# Measured corpus accuracy at the time this gate was set: 1.0000 (176/176).
# Gate = measured - 0.03. See test_corpus_regression_gate below.
CORPUS_ACCURACY_FLOOR = 0.97


def _ensure_routers_registered() -> None:
    """main.py is owned by the integrator; until the routers are wired in
    there, mount them on the shared app here so the tests can run."""
    paths = {getattr(r, "path", None) for r in app.routes}
    if "/sandbox/triage" not in paths:
        app.include_router(sandbox_router)
    if "/eval/summary" not in paths:
        app.include_router(evaluation_router)


SEPSIS_NOTE = (
    "72yo with fever 39.4, BP 88/52, lactate 3.1, WBC 18. Meets SIRS. "
    "IV fluids 30 mL/kg initiated."
)

EVAL_SEED = [
    {
        "id": "E-001",
        "note_text": SEPSIS_NOTE,
        "template_name": "sepsis_no_abx",
        "truth_bottleneck": "missing_soc",   # predicted: missing_soc (correct)
    },
    {
        "id": "E-002",
        "note_text": (
            "38yo female, 2 days of dysuria. Afebrile. UA positive. "
            "Discharge home on nitrofurantoin."
        ),
        "template_name": "clear_uti",
        "truth_bottleneck": "clear",         # predicted: clear (correct)
    },
    {
        "id": "E-003",
        "note_text": (
            "58yo male with right lower quadrant abdominal pain. Afebrile, "
            "hemodynamically normal. CT abdomen ordered 5h ago, still pending "
            "in radiology queue. Disposition depends on the study."
        ),
        "template_name": "rlq_ct_pending",
        "truth_bottleneck": "awaiting_imaging",  # predicted: awaiting_imaging (correct)
    },
    {
        "id": "E-004",
        "note_text": (
            "44yo with type 2 diabetes admitted for leg cellulitis, improving "
            "on oral antibiotics. Home insulin glargine continued at prior "
            "doses. Anticipate routine course."
        ),
        "template_name": "insulin_no_glucose_monitor",
        "truth_bottleneck": "med_risk",      # predicted: clear (deliberate miss)
    },
]


@pytest.fixture(scope="module")
def client():
    _ensure_routers_registered()
    c, _session = build_test_client(seed_patients=EVAL_SEED)
    yield c
    teardown_test_client()


# ---------------------------------------------------------------------------
# Sandbox
# ---------------------------------------------------------------------------

def test_sandbox_triage_sepsis_note(client):
    r = client.post("/sandbox/triage", json={"note_text": SEPSIS_NOTE, "age": 72, "sex": "F"})
    assert r.status_code == 200
    body = r.json()

    primary = body["triage"]["primary"]
    assert primary["category"] == "missing_soc"
    assert primary["urgency"] == "red"
    assert primary["owner"] == "physician"
    # Evidence spans must point back into the pasted note
    assert len(primary["evidence"]) > 0
    span = primary["evidence"][0]
    assert SEPSIS_NOTE[span["start"]:span["end"]] == span["text"]

    # Extraction trace present
    assert any(l["label"] == "lactate" for l in body["extraction"]["labs"])

    # Stage timings present and sane
    timings = body["stage_timings_ms"]
    assert set(timings) == {"extract", "classify", "icd", "total"}
    assert all(v >= 0 for v in timings.values())
    assert timings["total"] >= max(timings["extract"], timings["classify"], timings["icd"])

    # Engine metadata
    assert body["engine"] == {
        "protocols_evaluated": 12,
        "categories": 7,
        "version": "0.1.0",
    }

    # ICD candidates carry the contract fields
    for c in body["icd_candidates"]:
        assert set(c) == {"code", "description", "score", "category"}


def test_sandbox_triage_rejects_short_note(client):
    r = client.post("/sandbox/triage", json={"note_text": "too short"})
    assert r.status_code == 422


def test_sandbox_samples(client):
    r = client.get("/sandbox/samples")
    assert r.status_code == 200
    samples = r.json()
    assert len(samples) >= 6
    categories = {s["expected_category"] for s in samples}
    assert len(categories) >= 6
    for s in samples:
        assert set(s) == {"key", "label", "note_text", "expected_category"}
        assert len(s["note_text"]) >= 20
        # Every sample must reproduce its expected category in the sandbox
        rr = client.post("/sandbox/triage", json={"note_text": s["note_text"]})
        assert rr.status_code == 200
        assert rr.json()["triage"]["primary"]["category"] == s["expected_category"]


def test_negation_showcase_sample_shows_neg_tags(client):
    """The negation-showcase sample is the demo's NegEx beat — it must produce
    visible NEG-tagged findings (chest pain + melena, both ruled out)."""
    samples = client.get("/sandbox/samples").json()
    showcase = next((s for s in samples if s["key"] == "negation_showcase"), None)
    assert showcase is not None, "negation_showcase sample missing"
    run = client.post("/sandbox/triage", json={"note_text": showcase["note_text"]}).json()
    findings = [f for group in run["extraction"].values() for f in group]
    negated = {f["label"] for f in findings if f.get("metadata", {}).get("negated")}
    assert negated, "negation showcase must yield at least one NEG-tagged finding"
    assert run["triage"]["primary"]["category"] == "missing_soc"


# ---------------------------------------------------------------------------
# Eval harness
# ---------------------------------------------------------------------------

def test_eval_summary_math(client):
    r = client.get("/eval/summary")
    assert r.status_code == 200
    body = r.json()

    assert body["n"] == 4
    assert body["accuracy"] == 0.75  # 3 of 4 engineered notes classify correctly

    metrics = {m["category"]: m for m in body["per_category"]}
    assert metrics["missing_soc"]["support"] == 1
    assert metrics["missing_soc"]["precision"] == 1.0
    assert metrics["missing_soc"]["recall"] == 1.0
    assert metrics["missing_soc"]["f1"] == 1.0

    assert metrics["awaiting_imaging"]["support"] == 1
    assert metrics["awaiting_imaging"]["recall"] == 1.0

    # med_risk: 1 truth, 0 predictions -> recall 0, precision 0
    assert metrics["med_risk"]["support"] == 1
    assert metrics["med_risk"]["recall"] == 0.0
    assert metrics["med_risk"]["precision"] == 0.0
    assert metrics["med_risk"]["f1"] == 0.0

    # clear: 1 truth, 2 predictions (E-002 correct + E-004 miss) -> precision 0.5
    assert metrics["clear"]["support"] == 1
    assert metrics["clear"]["precision"] == 0.5
    assert metrics["clear"]["recall"] == 1.0

    cells = {(c["truth"], c["predicted"]): c["count"] for c in body["confusion"]}
    assert cells == {
        ("missing_soc", "missing_soc"): 1,
        ("awaiting_imaging", "awaiting_imaging"): 1,
        ("clear", "clear"): 1,
        ("med_risk", "clear"): 1,
    }

    # Owner routing: E-001 physician, E-002 "", E-003 nurse all correct;
    # E-004 expected pharmacist but routed "" -> 3/4.
    assert body["owner_routing"] == {"n": 4, "accuracy": 0.75}


def test_eval_misses(client):
    r = client.get("/eval/misses")
    assert r.status_code == 200
    misses = r.json()
    # E-001/E-002/E-003 are owner-correct; E-004 is a category miss. No owner
    # misses in this fixture, so the only row is the category miss.
    assert misses == [
        {
            "patient_id": "E-004",
            "miss_type": "category",
            "truth": "med_risk",
            "predicted": "clear",
            "urgency": "green",
            "template_name": "insulin_no_glucose_monitor",
        }
    ]


# ---------------------------------------------------------------------------
# Corpus regression gate
# ---------------------------------------------------------------------------

def test_corpus_regression_gate():
    """QUALITY GATE for rule edits.

    Runs the pure pipeline (no DB) over the full shipped corpus and compares
    primary_category to truth_bottleneck. If an extractor / protocol /
    classifier change drops corpus accuracy below the floor, this test fails
    and the rule edit needs justification (or the floor consciously re-set
    after re-measuring).
    """
    rows = json.loads(NOTES_PATH.read_text())
    labeled = [r for r in rows if r.get("truth_bottleneck")]
    assert len(labeled) >= 100  # the corpus itself should not silently shrink

    correct = 0
    for row in labeled:
        note = row["note_text"]
        predicted = classify(note, extract(note)).primary.category
        if predicted == row["truth_bottleneck"]:
            correct += 1

    accuracy = correct / len(labeled)
    assert accuracy >= CORPUS_ACCURACY_FLOOR, (
        f"Corpus accuracy regressed: {accuracy:.4f} < floor {CORPUS_ACCURACY_FLOOR} "
        f"({correct}/{len(labeled)} correct)"
    )
