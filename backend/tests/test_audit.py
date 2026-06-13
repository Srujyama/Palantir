"""Provenance / audit export tests.

These tests are the executable form of the "verifiable, not a black box"
thesis. They seed a real patient through the real pipeline (via
build_test_client), then prove every surfaced signal traces back to a
guideline citation and a *verified* evidence span — note[start:end] == text.

If pct_verified is ever below 100 that is a REAL bug in the extraction /
classification path, not a flaky test. The assertions report the offending
patient + span loudly rather than relaxing the bar.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from tests.conftest import build_test_client, teardown_test_client


# A self-contained sepsis note that reliably triggers the Surviving Sepsis
# Campaign protocol with a missing-antibiotics silent failure. Mirrors the
# shipped corpus's sepsis template so the test does not depend on corpus state.
SEPSIS_NOTE = (
    "HPI: 72yo presenting from SNF with fever to 39.4C, BP 88/52, HR 122, "
    "RR 24, SpO2 91% on room air. Family reports two days of decreased PO "
    "intake and confusion. PMH: HTN, DM2, recurrent UTI.\n"
    "Exam: ill-appearing, dry mucous membranes. Mild suprapubic tenderness.\n"
    "Labs: WBC 18.2, lactate 3.1, creatinine 1.9 (baseline 1.0), UA cloudy "
    "with many bacteria and 50+ WBC/hpf. Blood cultures drawn.\n"
    "Imaging: CXR no infiltrate.\n"
    "Assessment: severe sepsis, urinary source. Meets SIRS criteria with "
    "end-organ dysfunction.\n"
    "Plan: IV fluids 30 mL/kg bolus initiated. Will trend lactate. Admit to "
    "medicine."
)


def _seed():
    return build_test_client(
        seed_patients=[
            {
                "id": "P-AUD1",
                "age": 72,
                "sex": "F",
                "chief_complaint": "Fever, hypotension",
                "note_text": SEPSIS_NOTE,
                "arrival_time": datetime.utcnow() - timedelta(hours=6),
                "template_name": "sepsis_no_abx",
                "truth_bottleneck": "missing_soc",
            }
        ]
    )


def test_patient_audit_returns_cited_verified_signals():
    client, _ = _seed()
    try:
        resp = client.get("/audit/patient/P-AUD1")
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["patient_id"] == "P-AUD1"
        assert data["note_text"] == SEPSIS_NOTE
        assert data["signals"], "sepsis patient should surface at least one signal"

        # Every signal carries a citation tracing to a guideline.
        for sig in data["signals"]:
            assert sig["citation"], f"signal without citation: {sig}"
            # The provenance shape must be one of the three known sources.
            assert sig["source"] in {"primary", "secondary", "silent_failure"}
            assert sig["category"]
            assert sig["urgency"] in {"red", "amber", "green"}

        # The headline auditability invariant: every evidence span verifies.
        for sig in data["signals"]:
            for span in sig["evidence_spans"]:
                assert span["verified"] is True, (
                    f"span failed to verify: {span} note slice="
                    f"{SEPSIS_NOTE[span['start']:span['end']]!r}"
                )
                assert SEPSIS_NOTE[span["start"]:span["end"]] == span["text"]

        # There is a silent-failure signal (missing antibiotics) with a span.
        sf_signals = [s for s in data["signals"] if s["source"] == "silent_failure"]
        assert sf_signals, "expected a silent_failure signal for the sepsis bundle"
        assert any(s["evidence_spans"] for s in sf_signals)

        # Per-patient roll-up math is internally consistent.
        assert data["n_signals"] == len(data["signals"])
        assert data["n_with_citation"] == sum(
            1 for s in data["signals"] if s["citation"]
        )
        total_spans = sum(len(s["evidence_spans"]) for s in data["signals"])
        verified = sum(
            1 for s in data["signals"] for sp in s["evidence_spans"] if sp["verified"]
        )
        assert data["n_evidence_spans"] == total_spans
        assert data["n_verified_spans"] == verified
        assert data["pct_verified"] == 100.0
    finally:
        teardown_test_client()


def test_patient_audit_404_on_missing_patient():
    client, _ = _seed()
    try:
        resp = client.get("/audit/patient/P-DOES-NOT-EXIST")
        assert resp.status_code == 404
    finally:
        teardown_test_client()


def test_corpus_summary_math_and_full_verification():
    # Seed a mix: a sepsis patient (cited signals + spans) and a clear UTI
    # patient (no bottleneck). pct_verified must be 100 across the corpus.
    client, _ = build_test_client(
        seed_patients=[
            {
                "id": "P-AUD1",
                "note_text": SEPSIS_NOTE,
                "chief_complaint": "Fever, hypotension",
                "truth_bottleneck": "missing_soc",
            },
            {
                "id": "P-AUD2",
                "note_text": (
                    "38yo female, 2 days of dysuria. Afebrile. UA positive. "
                    "Discharge home on nitrofurantoin."
                ),
                "chief_complaint": "Uncomplicated UTI",
                "truth_bottleneck": "clear",
            },
        ]
    )
    try:
        resp = client.get("/audit/corpus/summary")
        assert resp.status_code == 200, resp.text
        s = resp.json()

        assert s["n_patients"] == 2
        assert s["n_signals"] >= 1
        # Internal consistency of the aggregate ratios.
        assert s["n_with_citation"] <= s["n_signals"]
        assert s["n_verified_spans"] <= s["n_evidence_spans"]
        assert s["n_evidence_spans"] >= 1

        expected_pct_cited = round(
            100.0 * s["n_with_citation"] / s["n_signals"], 2
        )
        assert s["pct_cited"] == expected_pct_cited

        expected_pct_verified = round(
            100.0 * s["n_verified_spans"] / s["n_evidence_spans"], 2
        )
        assert s["pct_verified"] == expected_pct_verified

        # The bar: every span verifies. A failure here is a real bug — report
        # the exact offenders, do not weaken the assertion.
        assert s["pct_verified"] == 100.0, (
            f"pct_verified < 100; unverified spans: {s.get('unverified_spans')}"
        )
        assert s["n_verified_spans"] == s["n_evidence_spans"]
        assert s["unverified_spans"] == []

        # Every guideline-backed recommendation is cited. With only protocol /
        # interaction signals seeded here, that is 100%.
        assert s["pct_cited"] == 100.0
    finally:
        teardown_test_client()


def test_corpus_summary_empty_db_is_vacuously_clean():
    client, _ = build_test_client(seed_patients=[])
    try:
        resp = client.get("/audit/corpus/summary")
        assert resp.status_code == 200
        s = resp.json()
        assert s["n_patients"] == 0
        assert s["n_signals"] == 0
        assert s["n_evidence_spans"] == 0
        # Zero-denominator convention: vacuously fully verified / cited.
        assert s["pct_verified"] == 100.0
        assert s["pct_cited"] == 100.0
        assert s["unverified_spans"] == []
    finally:
        teardown_test_client()
