"""Tests for the ICD-10 candidate matcher."""

from app.nlp.icd_matcher import expand_abbreviations, matcher


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


def test_aki_abbreviation_retrieves_kidney_codes():
    """`AKI` never appears in ICD descriptions — the abbreviation expansion
    must bridge it to N17 (acute kidney failure) in the top 5."""
    note = "68yo with AKI, creatinine rising on home lisinopril and ibuprofen."
    matches = matcher().match(note, k=5)
    codes = [m.code for m in matches]
    assert any(c.startswith("N17") for c in codes), \
        f"expected an N17 code in top 5, got {codes}"


def test_gib_abbreviation_retrieves_bleeding_codes():
    note = "81yo with GIB, hgb dropped to 7.9 overnight."
    matches = matcher().match(note, k=5)
    descriptions = " ".join(m.description.lower() for m in matches)
    assert "hemorrhage" in descriptions or "bleeding" in descriptions, \
        f"expected GI-bleed retrieval, got {[m.code for m in matches]}"


def test_expand_abbreviations_appends_and_preserves_original():
    note = "68yo with AKI and CHF exacerbation."
    expanded = expand_abbreviations(note)
    # Original text is preserved verbatim at the start — offsets unaffected.
    assert expanded.startswith(note)
    assert "acute kidney injury" in expanded
    assert "congestive heart failure" in expanded


def test_expand_abbreviations_noop_without_abbreviations():
    note = "Generic admission note for fever and weakness."
    assert expand_abbreviations(note) == note


def test_expand_abbreviations_uppercase_only_for_acronyms():
    """Lowercase English words must not trigger all-caps acronym expansions
    ('af' fragment vs AF, 'us' vs US-style pitfalls)."""
    note = "Patient safe after transfer; pet care arranged."
    assert expand_abbreviations(note) == note
