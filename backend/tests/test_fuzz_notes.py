"""Adversarial note fuzzing.

Property tests (test_properties.py) stitch synthetic fragments. This file goes
after the *real* corpus and mutates it the way charts actually get mangled in
the wild: truncated mid-sentence, sentences duplicated, lines shuffled,
negations injected ("denies ...", "ruled out"), case flipped, whitespace and
punctuation churned. For every mutant we assert the two hard guarantees:

  * the pipeline never crashes, and
  * every evidence span still satisfies note[start:end] == text.

Plus a batch of thousands of random token-soup notes — the kind of input a
note never should be, but which a "verifiable, not a black box" system must
survive without an exception and with a valid output shape.

Generation is seeded (random.Random(FUZZ_SEED)) so a failure is reproducible.
The iteration count is asserted and printed so the run is auditable. We do NOT
assert that mutations preserve the classification — mutation can legitimately
change the answer (injecting a negation can clear a trigger). We assert only
the two invariants that must hold for ANY string.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from app.nlp.extractor import Span, extract
from app.services.bottleneck import BOTTLENECK_LABELS, classify


FUZZ_SEED = 1337

VALID_OWNERS = {"physician", "nurse", "pharmacist", "case_manager", "social_worker", ""}
VALID_URGENCIES = {"red", "amber", "green"}
VALID_CATEGORIES = set(BOTTLENECK_LABELS.keys())

# How many mutations to generate per real corpus note, and how many random
# token-soup notes to hammer. Asserted at the bottom so the count is part of
# the test contract, not just a comment.
MUTATIONS_PER_NOTE = 24
TOKEN_SOUP_ITERATIONS = 3000


_CORPUS_PATH = Path(__file__).resolve().parents[1] / "app" / "data" / "patient_notes.json"


def _load_corpus_notes():
    data = json.loads(_CORPUS_PATH.read_text())
    return [row["note_text"] for row in data if row.get("note_text")]


CORPUS_NOTES = _load_corpus_notes()

# Vocabulary for token soup — clinical-ish tokens plus structural noise so the
# soup actually probes the regexes rather than only the empty path.
_SOUP_TOKENS = [
    "BP", "88/52", "HR", "122", "WBC", "18.2", "lactate", "3.1", "sepsis",
    "SIRS", "fever", "troponin", "0.42", "chest", "pain", "stroke", "CVA",
    "tPA", "AKI", "creatinine", "2.4", "ibuprofen", "tobramycin", "contrast",
    "apixaban", "warfarin", "INR", "4.2", "melena", "QTc", "520", "ms",
    "potassium", "6.1", "lisinopril", "furosemide", "insulin", "glucose",
    "54", "CT", "MRI", "consult", "pending", "awaiting", "callback", "SNF",
    "placement", "DKA", "COPD", "denies", "ruled", "out", "no", "not",
    "resolved", "stable", "afebrile", ".", ",", "\n", ";", "/", "-",
    "\x00", "\t", "💉", "ünïcödé", "AAAAAAAA",
]

_NEGATION_INJECTIONS = [
    "denies ", "no ", "ruled out ", "negative for ", "without ",
    "patient denies any ", "exam negative for ",
]


def _assert_span_audits(note: str, span: Span) -> None:
    assert isinstance(span.start, int) and isinstance(span.end, int)
    assert 0 <= span.start <= span.end <= len(note), (
        f"span out of bounds {span} for note length {len(note)}"
    )
    assert note[span.start:span.end] == span.text, (
        f"span mismatch stored={span.text!r} "
        f"actual={note[span.start:span.end]!r}"
    )


def _all_spans(note: str):
    ext = extract(note)
    result = classify(note, ext)
    for b in [result.primary] + result.secondary:
        for s in b.evidence:
            yield s
    for sf in result.silent_failures:
        yield sf.trigger_evidence
    return result


def _assert_pipeline_ok(note: str) -> None:
    """The full contract for an arbitrary string: no crash, valid output
    shape, every span audits."""
    ext = extract(note)
    result = classify(note, ext)

    bottlenecks = [result.primary] + result.secondary
    for b in bottlenecks:
        assert b.category in VALID_CATEGORIES, f"bad category {b.category!r}"
        assert b.urgency in VALID_URGENCIES, f"bad urgency {b.urgency!r}"
        assert b.owner in VALID_OWNERS, f"bad owner {b.owner!r}"
        for s in b.evidence:
            _assert_span_audits(note, s)
    for sf in result.silent_failures:
        assert sf.urgency in VALID_URGENCIES
        assert sf.owner in VALID_OWNERS
        _assert_span_audits(note, sf.trigger_evidence)


# ---------------------------------------------------------------------------
# Mutators. Each takes (note, rng) -> mutated note.
# ---------------------------------------------------------------------------

def _mut_truncate(note: str, rng: random.Random) -> str:
    if not note:
        return note
    cut = rng.randint(0, len(note))
    return note[:cut]


def _mut_truncate_tail(note: str, rng: random.Random) -> str:
    if not note:
        return note
    cut = rng.randint(0, len(note))
    return note[cut:]


def _mut_duplicate_sentences(note: str, rng: random.Random) -> str:
    sentences = [s for s in note.replace("\n", ". ").split(". ") if s]
    if not sentences:
        return note + note
    times = rng.randint(2, 4)
    chosen = rng.sample(sentences, k=min(len(sentences), rng.randint(1, len(sentences))))
    return ". ".join(sentences + chosen * times)


def _mut_shuffle_lines(note: str, rng: random.Random) -> str:
    lines = note.split("\n")
    rng.shuffle(lines)
    return "\n".join(lines)


def _mut_inject_negation(note: str, rng: random.Random) -> str:
    lines = note.split("\n")
    if not lines:
        return note
    idx = rng.randrange(len(lines))
    lines[idx] = rng.choice(_NEGATION_INJECTIONS) + lines[idx]
    return "\n".join(lines)


def _mut_flip_case(note: str, rng: random.Random) -> str:
    return "".join(
        c.swapcase() if rng.random() < 0.3 else c for c in note
    )


def _mut_churn_whitespace(note: str, rng: random.Random) -> str:
    out = []
    for c in note:
        out.append(c)
        if c == " " and rng.random() < 0.2:
            out.append(rng.choice([" ", "\n", "\t"]))
    return "".join(out)


def _mut_insert_noise(note: str, rng: random.Random) -> str:
    if not note:
        return rng.choice(_SOUP_TOKENS)
    pos = rng.randrange(len(note) + 1)
    noise = " " + " ".join(rng.choice(_SOUP_TOKENS) for _ in range(rng.randint(1, 6))) + " "
    return note[:pos] + noise + note[pos:]


_MUTATORS = [
    _mut_truncate,
    _mut_truncate_tail,
    _mut_duplicate_sentences,
    _mut_shuffle_lines,
    _mut_inject_negation,
    _mut_flip_case,
    _mut_churn_whitespace,
    _mut_insert_noise,
]


def _mutate(note: str, rng: random.Random) -> str:
    """Apply 1..3 random mutators in sequence."""
    n = rng.randint(1, 3)
    out = note
    for _ in range(n):
        out = rng.choice(_MUTATORS)(out, rng)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_corpus_is_present():
    assert CORPUS_NOTES, "expected real corpus notes at app/data/patient_notes.json"


def test_real_corpus_notes_audit_unmutated():
    """Sanity floor: every shipped corpus note must already satisfy the
    invariants before we start mutating."""
    for note in CORPUS_NOTES:
        _assert_pipeline_ok(note)


def test_mutated_corpus_notes_never_crash_and_spans_stay_valid():
    rng = random.Random(FUZZ_SEED)
    iterations = 0
    for note in CORPUS_NOTES:
        for _ in range(MUTATIONS_PER_NOTE):
            mutant = _mutate(note, rng)
            _assert_pipeline_ok(mutant)
            iterations += 1
    # The iteration count is part of the contract: prove we actually fuzzed.
    assert iterations == len(CORPUS_NOTES) * MUTATIONS_PER_NOTE
    assert iterations >= 1000, f"too few mutation iterations: {iterations}"


def test_token_soup_batch_never_crashes_with_valid_shape():
    rng = random.Random(FUZZ_SEED + 1)
    for _ in range(TOKEN_SOUP_ITERATIONS):
        length = rng.randint(0, 60)
        note = " ".join(rng.choice(_SOUP_TOKENS) for _ in range(length))
        _assert_pipeline_ok(note)


def test_random_byte_strings_never_crash():
    """Raw, structureless input: control chars, high codepoints, the lot."""
    rng = random.Random(FUZZ_SEED + 2)
    for _ in range(1000):
        length = rng.randint(0, 300)
        note = "".join(chr(rng.randint(0, 0x2FFF)) for _ in range(length))
        _assert_pipeline_ok(note)


def test_fuzz_iteration_budget_is_substantial():
    """Document & enforce the total adversarial iteration budget so a future
    edit can't quietly gut the fuzzing."""
    total = (
        len(CORPUS_NOTES) * MUTATIONS_PER_NOTE  # mutated corpus
        + TOKEN_SOUP_ITERATIONS                 # token soup
        + 1000                                  # random byte strings
    )
    assert total >= 5000, f"fuzz budget too small: {total}"
