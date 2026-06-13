"""Tests for the longitudinal trend engine.

The contract: trends narrate trajectory from prior notes but NEVER change the
classifier's verdict. These tests pin the direction/clinical math, the
recurrence detector, resolved-gap detection, and (critically) that adding
priors does not move the current-note classification.
"""

from __future__ import annotations

from app.services import trends
from app.services.trends import NoteInput
from app.nlp.extractor import extract
from app.services.bottleneck import classify


def _series(*notes):
    n = len(notes)
    return [NoteInput(t, hours_ago=(n - 1 - i) * 3) for i, t in enumerate(notes)]


def _lab(payload, label):
    return next((l for l in payload["labs"] if l["label"] == label), None)


def test_lactate_clearing_is_improving():
    p = trends.compute(_series(
        "Labs: lactate 4.1.",
        "Labs: lactate 3.1.",
        "Labs: lactate 2.2.",
    ))
    lac = _lab(p, "lactate")
    assert lac["direction"] == "falling"
    assert lac["clinical"] == "improving"
    assert "clearing" in lac["narrative"]
    assert lac["delta"] < 0


def test_creatinine_rising_is_worsening():
    p = trends.compute(_series(
        "Labs: creatinine 1.0.",
        "Labs: creatinine 1.9.",
        "Labs: creatinine 2.4.",
    ))
    cr = _lab(p, "creatinine")
    assert cr["direction"] == "rising"
    assert cr["clinical"] == "worsening"


def test_hemoglobin_polarity_flip():
    """Rising hemoglobin is improving (up_good), unlike rising creatinine."""
    p = trends.compute(_series(
        "Labs: hgb 7.2.",
        "Labs: hgb 9.0.",
        "Labs: hemoglobin 10.4.",
    ))
    hgb = _lab(p, "hemoglobin")
    assert hgb["direction"] == "rising"
    assert hgb["clinical"] == "improving"


def test_hemoglobin_falling_is_worsening():
    p = trends.compute(_series(
        "Labs: hgb 11.4.",
        "Labs: hgb 9.1.",
        "Labs: hemoglobin 7.2.",
    ))
    hgb = _lab(p, "hemoglobin")
    assert hgb["clinical"] == "worsening"


def test_stable_within_epsilon():
    p = trends.compute(_series(
        "Labs: glucose 142.",
        "Labs: glucose 148.",
    ))
    glu = _lab(p, "glucose")
    # 142 -> 148 is within the glucose epsilon floor (20) -> stable.
    assert glu["direction"] == "stable"


def test_missing_value_midseries_is_handled():
    # Lactate present in note 1 and 3, absent (not re-drawn) in note 2.
    p = trends.compute(_series(
        "Labs: lactate 4.0.",
        "Assessment: clinically improving, labs not re-drawn this shift.",
        "Labs: lactate 2.2.",
    ))
    lac = _lab(p, "lactate")
    assert lac is not None
    # The middle note has no value -> shown as "pending" in the arrow chain.
    assert "pending" in lac["narrative"]
    assert lac["direction"] == "falling"


def test_single_note_yields_no_trend_signal():
    p = trends.compute(_series("Labs: lactate 3.1, creatinine 1.9."))
    assert p["note_count"] == 1
    assert p["trajectory_signal"] == "none"
    # Single-note labs are insufficient for a direction.
    for l in p["labs"]:
        assert l["direction"] == "insufficient"


def test_empty_notes_well_formed():
    p = trends.compute([])
    assert p["note_count"] == 0
    assert p["labs"] == []
    assert p["trajectory_signal"] == "none"


def test_recurrence_detection():
    p = trends.compute(_series(
        "HPI: 34yo with type 1 DM, third DKA admission in 8 months.",
    ))
    assert p["recurrence"] is not None
    assert p["recurrence"]["ordinal"] == 3
    assert "month" in p["recurrence"]["window_phrase"].lower()


def test_resolved_gap_detected_across_notes():
    """A sepsis bundle step missing in the prior note but documented now must
    surface as a resolved gap — and NOT change classification."""
    earlier = (
        "72yo with sepsis, BP 88/52, lactate 4.1. Meets SIRS. "
        "Blood cultures drawn. IV fluids started."
        # no antibiotics documented yet
    )
    current = (
        "72yo with sepsis, BP 90/55, lactate 3.1. Meets SIRS. "
        "Blood cultures drawn. IV fluids 30 mL/kg given. "
        "Vancomycin and piperacillin-tazobactam administered."
        # antibiotics now documented -> that gap closed
    )
    notes = [NoteInput(earlier, hours_ago=4), NoteInput(current, hours_ago=0)]
    p = trends.compute(notes)
    resolved_actions = {g["action_label"] for g in p["resolved_gaps"]}
    assert any("antibiotic" in a.lower() for a in resolved_actions), \
        f"expected antibiotics gap closed, got {resolved_actions}"


def test_priors_do_not_change_classification():
    """The core safety invariant: compute() reads priors, classify() does not.
    The current-note verdict is identical whether or not priors exist."""
    current = (
        "HPI: 72yo with fever 39.4, BP 88/52, lactate 3.1. Meets SIRS. "
        "Blood cultures drawn. IV fluids initiated."
    )
    verdict = classify(current, extract(current)).primary.category
    # trends.compute over a multi-note series must not be able to affect this;
    # classify only ever sees `current`.
    trends.compute(_series("Labs: lactate 4.1.", current))
    verdict_again = classify(current, extract(current)).primary.category
    assert verdict == verdict_again == "missing_soc"
