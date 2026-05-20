"""Tests for the ICD-10 candidate matcher."""

from app.nlp.icd_matcher import matcher


def test_sepsis_note_returns_sepsis_codes():
    note = "72yo with severe sepsis, fever 39.4, lactate 3.1, BP 88/52. SIRS criteria with end-organ dysfunction."
    matches = matcher().match(note, k=5)
    codes = [m.code for m in matches]
    # Should return at least one sepsis-related code in the top 5
    assert any(c.startswith("A41") or c.startswith("R65") for c in codes)


def test_dka_note_returns_diabetes_codes():
    # Use a more descriptive note that aligns with ICD descriptions.
    note = (
        "T1DM patient with diabetic ketoacidosis. Glucose 512, ketoacidosis confirmed, "
        "anion gap 24. Severe diabetes complication."
    )
    matches = matcher().match(note, k=5)
    codes = [m.code for m in matches]
    # Should return at least one diabetes code in the top 5
    assert any(c.startswith("E10") or c.startswith("E11") for c in codes), \
        f"expected diabetes code in top 5, got {codes}"


def test_returns_at_most_k():
    note = "Generic admission note for fever and weakness."
    matches = matcher().match(note, k=3)
    assert len(matches) <= 3


def test_scores_descending():
    note = "Severe sepsis with hypotension and end-organ dysfunction. UA cloudy."
    matches = matcher().match(note, k=5)
    scores = [m.score for m in matches]
    assert scores == sorted(scores, reverse=True)
