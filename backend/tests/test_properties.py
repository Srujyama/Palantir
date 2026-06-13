"""Property-based invariants for the deterministic classification path.

The Bottleneck Radar's thesis is "verifiable, not a black box". A black box
can be defended with a few happy-path tests; a verifiable, deterministic
rule engine can be held to *invariants that must hold for every possible
input*. That is what this file does, with Hypothesis driving thousands of
generated notes (real clinical fragments stitched together, plus pathological
strings: empty, huge, unicode, control chars, repeated tokens).

The invariants:

  1. classify() never raises on ANY string.
  2. classify() is deterministic — same note -> identical
     category / urgency / owner across repeated calls.
  3. THE auditability invariant: every evidence Span returned anywhere
     (bottleneck evidence, silent_failure trigger_evidence) satisfies
     note[start:end] == text. This is what makes the highlight in the UI a
     proof, not a guess.
  4. urgency is always one of red/amber/green.
  5. category is always in the known set.
  6. owner is a valid owner or empty.
  7. leading/trailing whitespace does not change the category.
  8. a clear note stays clear under benign suffixes.

Run with: .venv/bin/python -m pytest tests/test_properties.py -q
"""

from __future__ import annotations

from dataclasses import asdict

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.nlp.extractor import Span, extract
from app.services.bottleneck import BOTTLENECK_LABELS, classify


VALID_OWNERS = {
    "physician",
    "nurse",
    "pharmacist",
    "case_manager",
    "social_worker",
}
VALID_URGENCIES = {"red", "amber", "green"}
VALID_CATEGORIES = set(BOTTLENECK_LABELS.keys())


# ---------------------------------------------------------------------------
# Note-fragment vocabulary. Realistic clinical tokens so generated notes
# exercise the actual regexes (triggers, meds, vitals) instead of only
# bouncing off the empty path. Stitched into notes by the strategies below.
# ---------------------------------------------------------------------------

_FRAGMENTS = [
    # Sepsis / infection
    "Meets SIRS criteria, severe sepsis.", "fever to 39.4C", "lactate 3.1",
    "WBC 18.2", "blood cultures drawn", "no antibiotics given yet",
    "septic shock", "BP 88/52", "HR 122",
    # Cardiac / ACS
    "chest pain", "troponin 0.42", "ST elevation", "aspirin given",
    "two negative troponins", "chest pain resolved",
    # Stroke
    "acute stroke", "facial droop", "NIHSS 8", "tPA window",
    "stroke resolved", "CVA", "hemiparesis",
    # AKI / renal
    "acute kidney injury", "creatinine 2.4", "AKI", "oliguria",
    "creatinine rising", "ibuprofen", "tobramycin", "contrast",
    # Meds / interactions
    "apixaban", "warfarin INR 4.2", "melena", "ondansetron", "azithromycin",
    "QTc 520 ms", "potassium 6.1", "lisinopril", "furosemide", "insulin",
    "glucose 54", "enoxaparin", "clopidogrel", "lorazepam", "fentanyl",
    "linezolid", "sertraline",
    # Operational
    "cardiology consult pending, awaiting callback",
    "CT abd pending", "MRI brain in queue", "awaiting imaging",
    "SNF placement declined", "insurance authorization pending",
    "medically ready for discharge", "home oxygen setup backlog",
    "third admission for DKA", "non-adherence", "lives alone",
    # COPD / DKA
    "COPD exacerbation, moderate", "DKA", "anion gap closed",
    "prednisone started", "duoneb", "DKA resolved",
    # Negation / benign
    "denies melena", "ruled out", "no acute distress", "stable",
    "afebrile", "improving",
]

# Tokens that should never on their own create a bottleneck; used to confirm
# whitespace/suffix invariants on genuinely clear notes.
_BENIGN_CLEAR_NOTE = (
    "38yo female, 2 days of dysuria. Afebrile, hemodynamically stable. "
    "UA positive. Discharge home on nitrofurantoin. No acute distress."
)
_BENIGN_SUFFIXES = [
    "", " ", "\n", "\n\n", "  ", "\t",
    " Patient resting comfortably.", "\nPlan: continue current management.",
    " Reviewed with attending.", "\n\n-- end of note --",
]


def _all_spans(note: str):
    """Yield every Span the pipeline attaches to this note, from every place
    a Span can appear: primary + secondary bottleneck evidence, and each
    silent_failure trigger_evidence."""
    ext = extract(note)
    result = classify(note, ext)
    for b in [result.primary] + result.secondary:
        for s in b.evidence:
            yield s
    for sf in result.silent_failures:
        yield sf.trigger_evidence


def _assert_span_audits(note: str, span: Span) -> None:
    assert isinstance(span.start, int) and isinstance(span.end, int)
    assert 0 <= span.start <= span.end <= len(note), (
        f"span out of bounds: {asdict(span)} (note len {len(note)})"
    )
    # THE invariant. If this ever fails the highlight in the UI would point at
    # the wrong characters — a verifiability defect, not a cosmetic one.
    assert note[span.start:span.end] == span.text, (
        f"span text mismatch: stored={span.text!r} "
        f"actual={note[span.start:span.end]!r}"
    )


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Realistic notes: 0..12 fragments joined by spaces/newlines.
_realistic_notes = st.lists(
    st.sampled_from(_FRAGMENTS), min_size=0, max_size=12
).map(lambda parts: " ".join(parts))

# Pathological strings: unicode, control chars, anything.
_arbitrary_text = st.text(min_size=0, max_size=2000)

# Repeated tokens / token soup of clinical-ish words.
_token_soup = st.lists(
    st.sampled_from(
        [t.split()[0] for t in _FRAGMENTS] + ["BP", "WBC", "CT", "MRI", "INR"]
    ),
    min_size=0,
    max_size=200,
).map(lambda toks: " ".join(toks))

_any_note = st.one_of(_realistic_notes, _arbitrary_text, _token_soup)


# ---------------------------------------------------------------------------
# Invariant 1: classify() never raises (incl. empty / huge / unicode / ctrl).
# ---------------------------------------------------------------------------

@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
@given(note=_any_note)
def test_classify_never_raises(note):
    ext = extract(note)
    classify(note, ext)  # must not raise


@settings(max_examples=60, suppress_health_check=[HealthCheck.too_slow])
@given(blob=st.text(alphabet=st.characters(), min_size=0, max_size=200))
def test_classify_never_raises_on_pure_unicode_and_controls(blob):
    # Explicitly include control chars and arbitrary unicode codepoints.
    ext = extract(blob)
    classify(blob, ext)


def test_classify_never_raises_on_extremes():
    for note in ["", " ", "\x00\x01\x02", "a" * 100_000, "💉🩺" * 5000, "\n" * 1000]:
        ext = extract(note)
        classify(note, ext)


# ---------------------------------------------------------------------------
# Invariant 2: determinism.
# ---------------------------------------------------------------------------

@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(note=_any_note)
def test_classify_is_deterministic(note):
    ext1 = extract(note)
    r1 = classify(note, ext1)
    ext2 = extract(note)
    r2 = classify(note, ext2)
    assert (r1.primary.category, r1.primary.urgency, r1.primary.owner) == (
        r2.primary.category,
        r2.primary.urgency,
        r2.primary.owner,
    )
    assert r1.primary.recommended_action == r2.primary.recommended_action
    assert [b.category for b in r1.secondary] == [b.category for b in r2.secondary]


# ---------------------------------------------------------------------------
# Invariant 3: every evidence span audits (note[start:end] == text).
# ---------------------------------------------------------------------------

@settings(max_examples=500, suppress_health_check=[HealthCheck.too_slow])
@given(note=_any_note)
def test_every_evidence_span_audits(note):
    for span in _all_spans(note):
        _assert_span_audits(note, span)


# ---------------------------------------------------------------------------
# Invariants 4-6: output domain (urgency / category / owner).
# ---------------------------------------------------------------------------

@settings(max_examples=400, suppress_health_check=[HealthCheck.too_slow])
@given(note=_any_note)
def test_output_domains(note):
    ext = extract(note)
    result = classify(note, ext)
    for b in [result.primary] + result.secondary:
        assert b.urgency in VALID_URGENCIES, f"bad urgency {b.urgency!r}"
        assert b.category in VALID_CATEGORIES, f"bad category {b.category!r}"
        assert b.owner in VALID_OWNERS or b.owner == "", f"bad owner {b.owner!r}"
    # Silent failures carry their own owner/urgency too.
    for sf in result.silent_failures:
        assert sf.urgency in VALID_URGENCIES
        assert sf.owner in VALID_OWNERS or sf.owner == ""


# ---------------------------------------------------------------------------
# Invariant 7: leading / trailing whitespace does not change category.
# ---------------------------------------------------------------------------

@settings(max_examples=300, suppress_health_check=[HealthCheck.too_slow])
@given(
    note=_realistic_notes,
    lead=st.sampled_from(["", " ", "  ", "\n", "\t", " \n "]),
    trail=st.sampled_from(["", " ", "  ", "\n", "\t", " \n "]),
)
def test_whitespace_padding_preserves_category(note, lead, trail):
    base = classify(note, extract(note))
    padded_text = f"{lead}{note}{trail}"
    padded = classify(padded_text, extract(padded_text))
    assert base.primary.category == padded.primary.category
    assert base.primary.urgency == padded.primary.urgency
    assert base.primary.owner == padded.primary.owner
    # Spans in the padded note still audit against the padded note.
    for span in _all_spans(padded_text):
        _assert_span_audits(padded_text, span)


# ---------------------------------------------------------------------------
# Invariant 8: a clear note stays clear under benign suffixes.
# ---------------------------------------------------------------------------

def test_clear_note_is_clear():
    result = classify(_BENIGN_CLEAR_NOTE, extract(_BENIGN_CLEAR_NOTE))
    assert result.primary.category == "clear", (
        f"baseline note unexpectedly classified {result.primary.category!r}"
    )


@settings(max_examples=len(_BENIGN_SUFFIXES))
@given(suffix=st.sampled_from(_BENIGN_SUFFIXES))
def test_clear_note_stays_clear_under_benign_suffix(suffix):
    note = _BENIGN_CLEAR_NOTE + suffix
    result = classify(note, extract(note))
    assert result.primary.category == "clear", (
        f"benign suffix {suffix!r} flipped a clear note to "
        f"{result.primary.category!r}"
    )
